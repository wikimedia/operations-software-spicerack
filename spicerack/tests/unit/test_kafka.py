"""Kafka Module test."""
from collections import namedtuple
from typing import List, Union
from unittest import mock

import pytest
from kafka import KafkaConsumer, TopicPartition
from kafka.structs import OffsetAndMetadata, OffsetAndTimestamp
from wmflib.config import load_yaml_config

from spicerack.kafka import DELTA, ConsumerDefinition, Kafka, KafkaError
from spicerack.tests import get_fixture_path

OFFSET = 2

TIMESTAMP = 12323847623

SimpleMessage = namedtuple("SimpleMessage", "timestamp offset")

test_data = [
    (
        (
            ["wikidata"],
            ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
            ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_2"),
        ),
        [({TopicPartition(topic="eqiad.wikidata", partition=0): OffsetAndMetadata(OFFSET, None)})],
    ),
    (
        (
            ["wikidata"],
            ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
            ConsumerDefinition("eqiad", "main", "consumer_main_2"),
        ),
        [({TopicPartition(topic="eqiad.wikidata", partition=0): OffsetAndMetadata((TIMESTAMP - DELTA) - 100, None)})],
    ),
    (
        (
            ["wikidata", "mediainfo"],
            ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
            ConsumerDefinition("eqiad", "main", "consumer_main_2"),
        ),
        [
            ({TopicPartition(topic="eqiad.wikidata", partition=0): OffsetAndMetadata((TIMESTAMP - DELTA) - 100, None)}),
            (
                {
                    TopicPartition(topic="eqiad.mediainfo", partition=0): OffsetAndMetadata(
                        (TIMESTAMP - DELTA) - 100, None
                    )
                }
            ),
        ],
    ),
    (
        (
            ["wikidata"],
            ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
            ConsumerDefinition("codfw", "main", "consumer_main_2"),
        ),
        [({TopicPartition(topic="codfw.wikidata", partition=0): OffsetAndMetadata((TIMESTAMP - DELTA) - 100, None)})],
    ),
]


def _answer_offsets_for_times(timestamps):
    return {tp: OffsetAndTimestamp(ts - 100, ts) for tp, ts in timestamps.items()}


def _answer_partitions_for_topic(topic) -> Union[List[int], None]:
    return [0] if topic.startswith("eqiad.") or topic.startswith("codfw.") else []


@mock.patch("ssl.SSLContext.load_verify_locations")
@mock.patch("spicerack.kafka.KafkaConsumer", autospec=True)
class TestKafka:
    """Test class for Kafka module."""

    def setup_method(self):
        """Set up the module under test."""
        # pylint: disable=attribute-defined-outside-init
        self.kafka = Kafka(kafka_config=load_yaml_config(get_fixture_path("kafka", "config.yaml")), dry_run=False)

    @pytest.mark.parametrize("func_arguments,expected_commit_params", test_data)
    def test_offset_transfer(self, consumer_patch, load_verify_locations_patch, func_arguments, expected_commit_params):
        """It should correctly transfer offsets between consumer groups."""
        to_consumer_mock = self._setup_consumer_mocks(
            consumer_patch, _answer_offsets_for_times, _answer_partitions_for_topic
        )

        self.kafka.transfer_consumer_position(*func_arguments)
        load_verify_locations_patch.assert_called()
        assert to_consumer_mock.commit.call_count == len(expected_commit_params)
        to_consumer_mock.commit.assert_has_calls(
            (mock.call(params) for params in expected_commit_params), any_order=True
        )

    @pytest.mark.parametrize("func_arguments", test_data)
    def test_offset_transfer_dry_run(self, consumer_patch, _, func_arguments):
        """It should read but not transfer offsets between consumer groups."""
        kafka = Kafka(kafka_config=load_yaml_config(get_fixture_path("kafka", "config.yaml")), dry_run=True)
        to_consumer_mock = self._setup_consumer_mocks(
            consumer_patch, _answer_offsets_for_times, _answer_partitions_for_topic
        )
        kafka.transfer_consumer_position(*func_arguments[0])
        assert not to_consumer_mock.commit.called

    def test_no_source_offset(self, consumer_patch, _):
        """It should raise an exception with specific message if no source offset available."""
        TestKafka._setup_empty_consumer_mocks(consumer_patch)
        with pytest.raises(
            expected_exception=KafkaError, match="Offset not found for topic eqiad.wikidata, partition 0."
        ):
            self.kafka.transfer_consumer_position(
                ["wikidata"],
                ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
                ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_2"),
            )

    def test_no_source_timestamp(self, consumer_patch, _):
        """It should raise an exception with specific message if no source timestamp available."""
        TestKafka._setup_empty_consumer_mocks(consumer_patch)
        with pytest.raises(
            expected_exception=KafkaError, match="Offset not found for topic eqiad.wikidata, partition 0."
        ):
            self.kafka.transfer_consumer_position(
                ["wikidata"],
                ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
                ConsumerDefinition("eqiad", "main", "consumer_jumbo_2"),
            )

    def test_no_destination_offset(self, consumer_patch, _):
        """It should raise an exception with specific message if no source timestamp available."""
        TestKafka._setup_consumer_mocks(
            consumer_patch, offset_for_times_answer=lambda x: {TopicPartition("eqiad.wikidata", 0): None}
        )
        with pytest.raises(
            expected_exception=KafkaError,
            match=f"Offset not found for topic eqiad.wikidata, partition 0, when seeking by timestamp {TIMESTAMP}.",
        ):
            self.kafka.transfer_consumer_position(
                ["wikidata"],
                ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
                ConsumerDefinition("eqiad", "main", "consumer_jumbo_2"),
            )

    def test_set_position_by_timestamp(self, consumer_patch, _):
        """It should approximate offset based on source timestamp."""
        consumer_mock = mock.MagicMock(spec_set=KafkaConsumer)
        consumer_mock.offsets_for_times.side_effect = _answer_offsets_for_times
        consumer_mock.partitions_for_topic.side_effect = _answer_partitions_for_topic
        consumer_patch.side_effect = [consumer_mock]
        self.kafka.set_consumer_position_by_timestamp(
            ConsumerDefinition("eqiad", "main", "consumer-group"), {"wikidata": TIMESTAMP, "mediainfo": TIMESTAMP + 10}
        )

        assert consumer_mock.commit.call_count == 2
        consumer_mock.commit.assert_has_calls(
            [
                mock.call(
                    {
                        TopicPartition(topic="eqiad.wikidata", partition=0): OffsetAndMetadata(
                            (TIMESTAMP - DELTA) - 100, None
                        )
                    }
                ),
                mock.call(
                    {
                        TopicPartition(topic="eqiad.mediainfo", partition=0): OffsetAndMetadata(
                            (TIMESTAMP - DELTA + 10) - 100, None
                        )
                    }
                ),
            ]
        )

    def test_no_topic_partitions(self, consumer_patch, _):
        """It should read but not transfer offsets between consumer groups."""
        kafka = Kafka(kafka_config=load_yaml_config(get_fixture_path("kafka", "config.yaml")), dry_run=False)
        self._setup_consumer_mocks(consumer_patch, _answer_offsets_for_times, lambda _: None)

        with pytest.raises(expected_exception=KafkaError, match="Partitions not found for topic eqiad.wikidata."):
            kafka.transfer_consumer_position(
                ["wikidata"],
                ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_1"),
                ConsumerDefinition("eqiad", "jumbo", "consumer_jumbo_2"),
            )

    @staticmethod
    def _setup_empty_consumer_mocks(consumer_patch):
        from_consumer_mock = mock.MagicMock(spec_set=KafkaConsumer)
        to_consumer_mock = mock.MagicMock(spec_set=KafkaConsumer)
        from_consumer_mock.partitions_for_topic.return_value = [0]
        from_consumer_mock.committed.return_value = None
        from_consumer_mock.__next__.return_value = None
        consumer_patch.side_effect = [from_consumer_mock, to_consumer_mock]

    @staticmethod
    def _setup_consumer_mocks(
        consumer_patch,
        offset_for_times_answer=_answer_offsets_for_times,
        answer_for_partition_for_topic=_answer_partitions_for_topic,
    ):
        from_consumer_mock = mock.MagicMock(spec_set=KafkaConsumer)
        from_consumer_mock.partitions_for_topic.side_effect = answer_for_partition_for_topic
        from_consumer_mock.__next__.return_value = SimpleMessage(timestamp=TIMESTAMP, offset=OFFSET)
        from_consumer_mock.committed.return_value = OFFSET
        to_consumer_mock = mock.MagicMock(spec_set=KafkaConsumer)
        to_consumer_mock.partitions_for_topic.side_effect = (
            lambda topic: [0] if topic.startswith("eqiad.") or topic.startswith("codfw.") else []
        )
        to_consumer_mock.offsets_for_times.side_effect = offset_for_times_answer
        consumer_patch.side_effect = [from_consumer_mock, to_consumer_mock]
        return to_consumer_mock
