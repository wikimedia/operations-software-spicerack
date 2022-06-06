"""Provides methods to manipulate offsets set for specific consumer groups."""
import logging
import ssl
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Set

from kafka import KafkaConsumer, OffsetAndMetadata, TopicPartition

from spicerack.exceptions import SpicerackError

TIMEOUT_MS = 20000
"""int: Timeout set for any kafka operations used in this module."""

DELTA = timedelta(minutes=2).seconds * 1000
"""int: For offset approximation, timestamp that will be used will be earlier by this amount of ms."""

logger = logging.getLogger(__name__)


@dataclass
class ConsumerDefinition:
    """Data needed to identify a Kafka Consumer.

    Arguments:
        site (str): Kafka site/DC.
        cluster (str): Kafka cluster.
        consumer_group (str): Kafka consumer group.

    """

    site: str
    cluster: str
    consumer_group: str


class KafkaError(SpicerackError):
    """Custom exception class for errors in this module."""


class KafkaClient:
    """Class encapsulating Kafka operations for specific site, cluster and consumer group."""

    _consumer: KafkaConsumer
    _site: str

    def __init__(self, consumer_definition: ConsumerDefinition, kafka_config: Dict, dry_run: bool) -> None:
        """Sets up a KafkaConsumer.

        Arguments:
            consumer_definition (spicerack.kafka.ConsumerDefinition): Definition of the Kafka data for the consumer.
            kafka_config (dict): Complete, available in Puppet, kafka definition.
            dry_run (bool): Enable dry run mode.

        """
        self._dry_run = dry_run
        self._site = consumer_definition.site
        context = ssl.create_default_context()
        context.check_hostname = False  # TODO can be changed after https://phabricator.wikimedia.org/T291905
        crt_location = "/etc/ssl/certs/ca-certificates.crt"
        context.load_verify_locations(crt_location)

        logger.debug(
            "Creating kafka client (kafka consumer with site prefix) with SSL context (check_hostname: %s, "
            "verify_mode: %s) for cluster and site: %s, %s",
            context.check_hostname,
            context.verify_mode,
            consumer_definition.cluster,
            consumer_definition.site,
        )
        brokers = kafka_config[consumer_definition.cluster][consumer_definition.site]["brokers"]["ssl_string"]
        self._consumer = KafkaConsumer(
            bootstrap_servers=brokers,
            enable_auto_commit=False,
            consumer_timeout_ms=TIMEOUT_MS,
            request_timeout_ms=TIMEOUT_MS,
            group_id=consumer_definition.consumer_group,
            security_protocol="SSL",
            ssl_context=context,
        )

    def _get_full_topic_name(self, topic: str) -> str:
        """Construct site specific full topic name.

        Arguments:
            topic (str): Topic name without site prefix.

        Returns:
            str: Topic name with site prefix.

        """
        return f"{self._site}.{topic}"

    def get_committed_offset(self, topic_partition: TopicPartition) -> int:
        """Retrieve a committed offset for given TopicPartition.

        Arguments:
            topic_partition (kafka.structs.TopicPartition): Non-localized topic partition.

        Returns:
            int: Last committed offset.

        """
        localized_tp = self._get_localized_tp(topic_partition)
        committed_offset = self._consumer.committed(localized_tp)
        if committed_offset is None:
            raise KafkaError(f"Offset not found for topic {localized_tp.topic}, partition {localized_tp.partition}.")

        return committed_offset

    def _get_localized_tp(self, topic_partition: TopicPartition) -> TopicPartition:
        """Translate provided TopicPartition into the one local to the cluster.

        Arguments:
            topic_partition (kafka.structs.TopicPartition): Non-localized topic partition.

        Returns:
            kafka.structs.TopicPartition: topic and partition localized for current site.

        """
        return TopicPartition(self._get_full_topic_name(topic_partition.topic), topic_partition.partition)

    def get_next_timestamp(self, topic_partition: TopicPartition) -> int:
        """Retrieve a timestamp for given TopicPartition.

        Arguments:
            topic_partition (kafka.structs.TopicPartition): Non-localized topic partition.

        Returns:
            int: Currently about to be processed timestamp.

        """
        localized_tp = self._get_localized_tp(topic_partition)
        self._consumer.assign([localized_tp])
        msg = next(self._consumer, None)
        if msg is None:
            raise KafkaError(f"Offset not found for topic {localized_tp.topic}, partition {localized_tp.partition}.")
        return msg.timestamp

    def partitions_for_topic(self, topic_name: str) -> Set[int]:
        """Get partitions for a localized provided topic.

        Arguments:
            topic_name (str): Topic name without site prefix.

        Returns:
            set[int]: Set of partitions available for given topic.

        """
        full_topic_name = self._get_full_topic_name(topic_name)
        topic_partitions = self._consumer.partitions_for_topic(full_topic_name)
        if not topic_partitions:
            raise KafkaError(f"Partitions not found for topic {full_topic_name}.")
        return topic_partitions

    def seek_offset(self, topic_partition: TopicPartition, offset: int) -> None:
        """Seek the provided partition for a configured consumer group to a specific offset.

        Arguments:
            topic_partition (kafka.structs.TopicPartition): Non-localized topic partition.
            offset (int): Desired offset.

        """
        local_tp = self._get_localized_tp(topic_partition)
        if self._dry_run:
            logger.debug(
                "dry_run mode: Attempted to commit on %s:%s to offset %s.",
                local_tp.topic,
                local_tp.partition,
                offset,
            )
        else:
            self._consumer.assign([local_tp])
            self._consumer.commit({local_tp: OffsetAndMetadata(offset, None)})

    def find_offset_for_timestamp(self, topic_partition: TopicPartition, timestamp: int) -> int:
        """Find offset by approximating it with the provided timestamp.

        Arguments:
            topic_partition (kafka.structs.TopicPartition): Non-localized topic partition.
            timestamp (int): Timestamp for offset approximation.

        Returns:
            int: Approximated offset.

        """
        local_tp = self._get_localized_tp(topic_partition)
        offset_timestamp = self._consumer.offsets_for_times({local_tp: timestamp - DELTA})
        if not offset_timestamp or not offset_timestamp[local_tp]:
            raise KafkaError(
                f"Offset not found for topic {local_tp.topic}, partition {local_tp.partition}, "
                f"when seeking by timestamp {timestamp}."
            )

        return offset_timestamp[local_tp].offset

    def __enter__(self) -> "KafkaClient":
        """Returns initiated instance."""
        return self

    def __exit__(self, *_: Any) -> None:
        """Close KafkaConsumer."""
        self._consumer.close(autocommit=False)


class Kafka:
    """Kafka module, that currently allows for inter and cross cluster consumer group position transfer."""

    def __init__(self, *, kafka_config: Dict[str, Dict[str, Dict]], dry_run: bool = True):
        """Create Kafka module instance.

        Kafka config is based on a Puppet generated config.yaml in spicerack configs. At minimum, it requires a
        ssl_string defined for each participating cluster, e.g.::

          main:
            eqiad:
               brokers:
                  ssl_string: "address:port,address:port"
                  ...

        Arguments:
              kafka_config (dict): Complete, available in Puppet, kafka definition.
              dry_run (bool, optional): Enable dry run mode.

        """
        self._dry_run = dry_run
        self._kafka_config = kafka_config

    @staticmethod
    def _get_offsets(*, client: KafkaClient, topics: List[str]) -> Dict[TopicPartition, int]:
        """Retrieves offsets for given topics, mutated for given site.

        Arguments:
            client (spicerack.kafka.KafkaClient): Kafka consumer and site prefix for a given cluster.
            topics (list[str]): List of topics (without site prefixes) to get offsets for.

        Returns:
            dict[kafka.structs.TopicPartition, int]: Mapping of topic partitions to their offsets for a given consumer.

        Raises:
            spicerack.kafka.KafkaError: When local offset couldn't be located (e.g. because of no messages).

        """
        topic_partitions = {}
        for tp in Kafka._get_topic_partitions(client=client, topics=topics):
            committed_offset = client.get_committed_offset(tp)
            topic_partitions[tp] = committed_offset
        return topic_partitions

    @staticmethod
    def _get_timestamps(client: KafkaClient, topics: List[str]) -> Dict[TopicPartition, int]:
        """Retrieves timestamps for given topics, mutated for given site.

        Arguments:
            client (spicerack.kafka.KafkaClient): Kafka consumer and site prefix for a given cluster.
            topics (list[str]): List of topics (without site prefixes) to get timestamps for.

        Returns:
            dict[kafka.structs.TopicPartition, int]: Mapping of topic partitions to their timestamps for a given
            consumer.

        Raises:
            spicerack.kafka.KafkaError: When there was no message to get timestamp from.

        """
        topic_partitions = {}
        for tp in Kafka._get_topic_partitions(client=client, topics=topics):
            topic_partitions[tp] = client.get_next_timestamp(tp)
        return topic_partitions

    @staticmethod
    def _get_topic_partitions(client: KafkaClient, topics: List[str]) -> List[TopicPartition]:
        """Generates a list of topic partitions for given topic list.

        Arguments:
            client (spicerack.kafka.KafkaClient): Kafka consumer and site prefix for a given cluster.
            topics (list[str]): List of topics (without site prefixes) to get partitions for.

        Returns:
            list[kafka.structs.TopicPartition]: List of topic partitions.

        """
        topic_partitions = []
        for topic in topics:
            for p in client.partitions_for_topic(topic):
                topic_partitions.append(TopicPartition(topic, p))
        return topic_partitions

    @staticmethod
    def _set_offsets(*, client: KafkaClient, offset_data: Dict[TopicPartition, int]) -> None:
        """Sets topic partitions offsets.

        Arguments:
            client (spicerack.kafka.KafkaClient): Kafka consumer for a given cluster.
            offset_data (dict[kafka.structs.TopicPartition, int]): Mapping of topic partitions to their timestamps
            for a given consumer.

        """
        for tp, offset in offset_data.items():
            client.seek_offset(tp, offset)

    def _set_timestamps_for_topics(self, *, client: KafkaClient, timestamps: Dict[str, int]) -> None:
        """Sets topic partitions offsets, based on timestamps (minus :py:const:`spicerack.kafka.DELTA`) and topic names.

        Arguments:
            client (spicerack.kafka.KafkaClient): Kafka consumer and site prefix for a given cluster.
            timestamps (dict[str, int]): Mapping of topics to their timestamps.

        """
        tp_timestamps = {}
        for topic, timestamp in timestamps.items():
            for p in client.partitions_for_topic(topic):
                tp = TopicPartition(topic, p)
                tp_timestamps[tp] = timestamp
        self._set_timestamps(client=client, timestamps=tp_timestamps)

    @staticmethod
    def _set_timestamps(*, client: KafkaClient, timestamps: Dict[TopicPartition, int]) -> None:
        """Sets topic partitions offsets, based on timestamps (minus :py:const:`spicerack.kafka.DELTA`).

        Arguments:
            client (spicerack.kafka.KafkaClient): Kafka consumer and site prefix for a given cluster.
            timestamps (dict[kafka.structs.TopicPartition, int]): Mapping of topic partitions to their timestamps.

        Raise:
            spicerack.kafka.KafkaError: When local offset couldn't be located (e.g. because of no messages).

        """
        for tp, timestamp in timestamps.items():
            offset = client.find_offset_for_timestamp(tp, timestamp)
            client.seek_offset(tp, offset)

    def transfer_consumer_position(
        self, topics: List[str], source_consumer: ConsumerDefinition, target_consumer: ConsumerDefinition
    ) -> None:
        """Transfers position from one Kafka consumer group to another.

        Same cluster position is an offset transfer, different cluster will involve approximation
        based on the source timestamp (with :py:const:`spicerack.kafka.DELTA` ms earlier seek time).

        All topics for which the transfer will happen are assumed to use site prefixes (e.g. eqiad.mutation).

        Arguments:
            topics (list[str]): List of topics to transfer from and to, without site prefixes.
            source_consumer (spicerack.kafka.ConsumerDefinition): Consumer definition for the source consumer group.
            target_consumer (spicerack.kafka.ConsumerDefinition): Consumer definition for the target consumer group.

        """
        with KafkaClient(
            consumer_definition=source_consumer, kafka_config=self._kafka_config, dry_run=self._dry_run
        ) as source_client, KafkaClient(
            consumer_definition=target_consumer, kafka_config=self._kafka_config, dry_run=self._dry_run
        ) as target_client:

            if (source_consumer.cluster, source_consumer.site) == (target_consumer.cluster, target_consumer.site):
                logger.info("Same cluster, setting offsets...")
                offset_data = Kafka._get_offsets(client=source_client, topics=topics)
                logger.info(
                    'Extracted offsets from source cluster "%s", site "%s" and consumer group "%s".',
                    source_consumer.cluster,
                    source_consumer.site,
                    source_consumer.consumer_group,
                )
                self._set_offsets(client=target_client, offset_data=offset_data)
                logger.info(
                    'Offsets set for target cluster "%s", site "%s" and consumer group "%s".',
                    target_consumer.cluster,
                    target_consumer.site,
                    target_consumer.consumer_group,
                )

            else:
                logger.info("Different clusters, approximating offsets based on timestamps...")
                from_offsets_timestamps = Kafka._get_timestamps(client=source_client, topics=topics)
                logger.info(
                    'Extracted timestamps from source cluster "%s", site "%s" and consumer group "%s".',
                    source_consumer.cluster,
                    source_consumer.site,
                    source_consumer.consumer_group,
                )
                self._set_timestamps(client=target_client, timestamps=from_offsets_timestamps)
                logger.info(
                    'Offsets approximated and set for target cluster "%s", site "%s" and consumer group "%s".',
                    target_consumer.cluster,
                    target_consumer.site,
                    target_consumer.consumer_group,
                )

        logger.info("Done.")

    def set_consumer_position_by_timestamp(
        self, target_consumer: ConsumerDefinition, timestamps: Dict[str, int]
    ) -> None:
        """Set an approximated offsets for given topics (provided without site prefix).

        Module uses timestamps earlier by :py:const:`spicerack.kafka.DELTA` ms.

        Arguments:
            target_consumer (spicerack.kafka.ConsumerDefinition): Consumer definition for the target consumer group.
            timestamps (dict[str, int): List of topics with timestamps to use.

        """
        with KafkaClient(
            consumer_definition=target_consumer, kafka_config=self._kafka_config, dry_run=self._dry_run
        ) as client:
            logger.info("Approximating offsets based on provided timestamps...")
            self._set_timestamps_for_topics(client=client, timestamps=timestamps)

        logger.info("Done.")
