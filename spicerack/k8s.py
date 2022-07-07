"""Kubernetes module."""
import logging
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import kubernetes  # mypy: no-type
from kubernetes import client, config  # mypy: no-type
from kubernetes.client.models import V1Taint

from spicerack.decorators import retry
from spicerack.exceptions import SpicerackCheckError, SpicerackError

logger = logging.getLogger(__name__)


class KubernetesApiError(SpicerackError):
    """Custom error class for errors interacting with the kubernetes api."""


class KubernetesApiTooManyRequests(KubernetesApiError):
    """Custom error class for HTTP TooManyRequest errors when interacting with the kubernetes api."""


class KubernetesError(SpicerackError):
    """Custom error class for errors in running the kubernetes module."""


class KubernetesCheckError(SpicerackCheckError):
    """Custom error class for errors checking kubernetes resources."""


class Kubernetes:
    """High-level interface for interacting with the kubernetes api from spicerack."""

    def __init__(self, group: str, cluster: str, *, dry_run: bool = True):
        """Initialize the instance.

        Arguments:
          group (string): the cluster group we want to operate on
          cluster (string): the cluster we're operating on
          dry_run (bool): if true, no write operations will happen.

        """
        self.group = group
        self.api = KubernetesApiFactory(cluster)
        self.dry_run = dry_run

    def get_node(self, name: str) -> "KubernetesNode":
        """Get an object for a kubernetes node.

        Arguments:
          name (string): the name of the node

        Returns:
          spicerack.kubernetes.KubernetesNode

        Raises:
          spicerack.kubernetes.KubernetesApiError if the node is not found on the cluster.

        """
        return KubernetesNode(name, self.api, self.dry_run)

    def get_pod(self, namespace: str, name: str) -> "KubernetesPod":
        """Get an object for a kubernetes pod.

        Arguments:
            name (string): the name of the pod
            namespace (string): the namespace the pod is in

        Returns:
            spicerack.kubernetes.KubernetesPod

        Raises:
            spicerack.kubernetes.KubernetesApiError if the pod is not found on the cluster

        """
        return KubernetesPod(namespace, name, self.api, self.dry_run)


class KubernetesApiFactory:
    """Provides kubernetes object classes easy access to the API."""

    API_CLASSES = {"core": client.CoreV1Api}
    CONFIG_BASE = "/etc/kubernetes"

    def __init__(self, cluster: str):
        """Initialize the instace.

        Arguments:
          cluster (string): the cluster we're operating on

        """
        self.cluster = cluster
        self._configurations: Dict[str, client.Configuration] = {}

    def configuration(self, user: str) -> client.Configuration:
        """Provide the configuration for a specific user.

        Arguments:
          user (string): the user to fetch the configuration for.

        Returns:
          kubernetes.client.Configuration: the configuration for the specified user.

        Raises:
          KubernetesError if the user or the configuration are invalid

        """
        # Check the user doesn't contain path separators
        if len(Path(user).parts) != 1:
            raise KubernetesError(f"User '{user}' is not valid")
        if user not in self._configurations:
            self._configurations[user] = client.Configuration()
            try:
                config.load_kube_config(
                    config_file=str(self._config_file_path(user)), client_configuration=self._configurations[user]
                )
            except kubernetes.config.config_exception.ConfigException as e:
                raise KubernetesError(e) from e
        return self._configurations[user]

    def core(self, *, user: str = "admin") -> kubernetes.client.CoreV1Api:
        """Return an instance of the core api correctly configured.

        Arguments:
          user (string): the user to use for authentication

        """
        conf = self.configuration(user)
        return self.API_CLASSES["core"](client.ApiClient(configuration=conf))

    def _config_file_path(self, user: str) -> Path:
        """Returns the path on the configuration file.

        Returns:
          pathlib.Path the path of the configuration file

        """
        return Path(self.CONFIG_BASE) / f"{user}-{self.cluster}.config"


class KubernetesNode:
    """Encapsulates actions on a kubernetes node."""

    def __init__(
        self,
        fqdn: str,
        api: KubernetesApiFactory,
        dry_run: bool = True,
        init_obj: Optional[kubernetes.client.models.v1_node.V1Node] = None,
    ):
        """Initialize the instance.

        Arguments:
          fqdn (string): the fqdn of the node.
          api (KubernetesApiFactory): the api factory we're going to use.
          dry_run (bool): if true, no write operations will happen.
          init_obj (kubernetes.client.models.v1_node.V1Node): if not None, this api object will be used, instead of
              fetching it from the api.

        """
        self._api = api
        self._fqdn = fqdn
        self._dry_run = dry_run
        if init_obj is not None:
            if init_obj.metadata.name != self._fqdn:
                raise KubernetesError(f"Mismatched names: got {init_obj.metadata.name}, expected {self._fqdn}")
            self._node = init_obj
        else:
            # Get the object corresponding to the fqdn provided. If non-existent, it will fail.
            self._node = self._get()

    def is_schedulable(self) -> bool:
        """Checks if a node is schedulable or not.

        Returns:
          bool true if payloads can be scheduled on the node, false otherwise.

        """
        return not (self._node.spec and self._node.spec.unschedulable)

    @property
    def name(self) -> str:
        """The name of the node.

        Returns:
          string: the name of the node.

        """
        return self._node.metadata.name

    @property
    def taints(self) -> List[V1Taint]:
        """The taints of the node.

        Returns:
          List[V1Taints]: the taints of the node.

        """
        return self._node.spec.taints if self._node.spec.taints is not None else []

    def cordon(self) -> None:
        """Makes the node unschedulable.

        Raises:
          KubernetesApiError if the call to the api failed
          KubernetesCheckError if the node wasn't set to unschedulable

        """
        if not self.is_schedulable():
            logger.info("Node %s already cordoned", self.name)
            return
        if self._dry_run:
            logger.info("Would have cordoned %s", self.name)
            return
        logger.info("Cordoning %s", self.name)
        body = {"spec": {"unschedulable": True}}
        self._node = self._patch(body)
        # Now let's check if the object has changed in the api as expected.
        if self.is_schedulable():
            raise KubernetesCheckError(f"{self} is not unschedulable after trying to cordon it.")

    def uncordon(self) -> None:
        """Makes a node schedulable.

        Raises:
          KubernetesApiError if the call to the api failed
          KubernetesCheckError if the node wasn't set to unschedulable

        """
        if self.is_schedulable():
            logger.info("Node %s already schedulable", self.name)
            return
        if self._dry_run:
            logger.info("Would have uncordoned %s", self.name)
            return
        logger.info("Uncordoning %s", self.name)
        body = {"spec": {"unschedulable": False}}
        self._node = self._patch(body)
        # Now let's check if the object has changed in the api as expected.
        if not self.is_schedulable():
            raise KubernetesCheckError(f"Node {self} is not schedulable after trying to uncordon it.")

    def drain(self) -> None:
        """Drains the node, analogous to `kubectl drain`.

        Raises:
          KubernetesCheckError if we can't evict all pods

        """
        unevictable: List["KubernetesPod"] = []
        failed: List[Tuple["KubernetesPod", KubernetesApiError]] = []
        self.cordon()
        max_grace_period = 0
        for pod in self.get_pods():
            try:
                # Dry run is passed to the pods, so if we're in dry-run mode nothing will actually be evicted.
                pod.evict()
            except KubernetesError:
                # pod.evict raises a KubernetesError if the pod is unevictable
                unevictable.append(pod)
            except KubernetesApiError as e:
                failed.append((pod, e))
            # Update the max grace period.
            if not pod.is_terminated() and pod.spec.termination_grace_period_seconds > max_grace_period:
                max_grace_period = pod.spec.termination_grace_period_seconds

        if len(failed) > 0:
            for p, exc in failed:
                logger.error("Failed to evict pod %s from node %s: %s", p, self, exc)

            raise KubernetesCheckError(f"Could not evict all pods from node {self}")

        self._wait_for_empty(len(unevictable), max_grace_period)

    def refresh(self) -> None:
        """Refresh the api object from the kubernetes api server."""
        self._node = self._get()

    def _get(self) -> kubernetes.client.models.v1_node.V1Node:
        """Get a node api object.

        Arguments:
          name (string): the name of the node

        Returns:
          kubernetes.client.models.v1_node.V1Node the api object for the node.

        """
        try:
            nodes = self._api.core().list_node(field_selector=f"metadata.name={self._fqdn}")
            nodes_found = len(nodes.items)
            if nodes_found == 1:
                return nodes.items[0]
            if nodes_found == 0:  # pylint: disable=no-else-raise
                raise KubernetesError(f"Node {self._fqdn} not found")
            else:
                node_names = ",".join([o.metadata.name for o in nodes.items])
                raise KubernetesError(f"More than one node found for name {self._fqdn}: {node_names}")
        except kubernetes.client.exceptions.ApiException as exc:
            raise KubernetesApiError(f"Failed to list nodes: {exc}") from exc

    def _patch(self, body: Dict[str, Any]) -> kubernetes.client.models.v1_node.V1Node:
        """Modify the node properties."""
        try:
            return self._api.core().patch_node(self.name, body)
        except kubernetes.client.exceptions.ApiException as exc:
            raise KubernetesApiError(f"Failed to modify node: {exc}") from exc

    def get_pods(self) -> List["KubernetesPod"]:
        """Get the pods running on this node."""
        pods = []
        try:
            for obj in self._api.core().list_pod_for_all_namespaces(field_selector=f"spec.nodeName={self.name}").items:
                p = KubernetesPod(
                    obj.metadata.namespace, obj.metadata.name, self._api, dry_run=self._dry_run, init_obj=obj
                )
                pods.append(p)
            return pods
        except kubernetes.client.exceptions.ApiException as exc:
            raise KubernetesApiError(f"Failed to find pods running on node {self.name}: {exc}") from exc

    def __str__(self) -> str:
        """String representation."""
        return f"Node({self._fqdn})"

    def _wait_for_empty(self, expected: int, max_grace_period: int) -> None:
        """Wait for all pods to be evicted."""
        if self._dry_run:
            logger.info("Would have waited for node %s to be empty", self.name)
            return

        def num_pods() -> int:
            return len([p for p in self.get_pods() if not p.is_terminated()])

        @retry(
            tries=3,
            backoff_mode="constant",
            exceptions=(KubernetesCheckError,),
            failure_message=f"Waiting for pods to be evicted from {self.name} ...",
        )
        def wait() -> None:
            npods = num_pods()
            if npods > expected:
                raise KubernetesCheckError(f"Node {self.name} still has {npods} pods, expected {expected}")

        # Wait for max grace period first, then retry 3 times (3 seconds delay) as pods need some time
        # to actually terminate.
        #
        # Please note that waiting for the max grace period is absolutely arbitrary and just what looks like
        # a reasonable time to wait for the api to conform its view of the node to reality.
        if num_pods() > expected:
            logger.debug("Waiting %d seconds before checking evictions again", max_grace_period)
            time.sleep(max_grace_period)
            wait()


class KubernetesPod:
    """Encapsulates actions on a kubernetes pod."""

    def __init__(
        self,
        namespace: str,
        name: str,
        api: KubernetesApiFactory,
        dry_run: bool = True,
        init_obj: Optional[kubernetes.client.models.v1_pod.V1Pod] = None,
    ):
        """Initialize the pod isntance.

        Arguments:
            namespace (string): the namespace where the pod is located.
            name (string): the name of the pod
            api (KubernetesApiFactory): the api factory we're going to use.
            dry_run (bool): if true, no write operations will happen.
            init_obj (kubernetes.client.models.v1_pod.V1Pod): if not None, this api object will be used, instead of
                fetching it from the api.

        """
        self._api = api
        self.name = name
        self.namespace = namespace
        self._dry_run = dry_run
        if init_obj is not None:
            if self.name != init_obj.metadata.name:
                raise KubernetesError(f"Mismatched names: got {init_obj.metadata.name}, expected {self.name}")
            if self.namespace != init_obj.metadata.namespace:
                raise KubernetesError(
                    f"Mismatched namespaces: {init_obj.metadata.namespace}, expected {self.namespace}"
                )
            self._pod = init_obj
        else:
            self._pod = self._get()

    @property
    def controller(self) -> Optional[kubernetes.client.models.v1_owner_reference.V1OwnerReference]:
        """Get the reference to the controlling object, if any.

        Returns:
          kubernetes.client.models.v1_owner_reference.V1OwnerReference: the reference.

        """
        ref = self._pod.metadata.owner_references
        if ref is None or len(ref) == 0:
            return None

        return ref[0]

    def is_daemonset(self) -> bool:
        """Checks if the pod is part of a daemonset.

        Returns:
          bool true if it is a daemonset, false otherwise.

        """
        if self.controller is None:
            return False
        return self.controller.kind == "DaemonSet"

    def is_terminated(self) -> bool:
        """Checks if the pod is terminated.

        Returns:
          bool true if the pod is not running, false otherwise.

        """
        return self._pod.status.phase in ["Succeeded", "Failed"]

    def is_mirror(self) -> bool:
        """Check if the pod is a mirror pod.

        Returns:
          bool true if this is a mirror pod, false otherwise.

        """
        return "kubernetes.io/config.mirror" in self._pod.metadata.annotations

    @property
    def spec(self) -> kubernetes.client.models.v1_pod_spec.V1PodSpec:
        """Acess the pod's spec.

        Returns:
          kubernetes.client.models.v1_pod_spec.V1PodSpec the pod spec

        """
        return self._pod.spec

    def is_evictable(self) -> bool:
        """Check if the pod can be evicted.

        Returns:
          bool  true if this pod can be evicted, false otherwise.

        """
        # We apply the logic found in kubectl:
        # https://github.com/kubernetes/kubernetes/blob/release-1.16/staging/src/k8s.io/kubectl/pkg/drain/filters.go
        # Check zero: a terminated pod is always evictable.
        if self.is_terminated():
            return True
        # Check one: the pod is orphaned and not finished
        if self.controller is None:
            logger.warning("Pod %s is orphaned, not evictable", self)
            return False
        # Check two: the pod is a daemonset
        if self.is_daemonset():
            logger.warning("Pod %s is a daemonset, not evictable", self)
            return False
        # Check three: the pod is a mirror
        if self.is_mirror():
            logger.warning("Pod %s is a mirror pod, not evictable", self)
            return False
        return True

    def evict(self) -> None:
        """Submit an eviction request to the kubernetes api for this pod.

        Raises:
          KubernetesApiTooManyRequests in case of a persistent HTTP 429 from the server.
          KubernetesApiError in case of a bad response from the server.
          KubernetesError if the pod is not evictable.

        """
        if not self.is_evictable():
            raise KubernetesError(f"Pod {self} is not evictable.")

        if self._dry_run:
            logger.info("Would have evicted %s", self)
            return
        logger.debug("Evicting pod %s", self)
        body = kubernetes.client.V1beta1Eviction(metadata=client.V1ObjectMeta(name=self.name, namespace=self.namespace))

        @retry(
            tries=4,
            backoff_mode="exponential",
            exceptions=(KubernetesApiTooManyRequests,),
            failure_message=f"Retrying eviction of {self}...",
        )
        def retry_evict() -> None:
            try:
                self._api.core().create_namespaced_pod_eviction(self.name, self.namespace, body)
            except kubernetes.client.exceptions.ApiException as e:
                # The eviction is not currently allowed because of a PodDisruptionBudget or
                # we hit an API rate limit.
                # In both cases we should retry the eviction.
                if e.status == HTTPStatus.TOO_MANY_REQUESTS:
                    logger.info("Failed to evict pod %s - HTTP response body: %s", self, e.body)
                    raise KubernetesApiTooManyRequests(e) from e
                raise KubernetesApiError(e) from e

        retry_evict()

    def _get(self) -> kubernetes.client.models.v1_pod.V1Pod:
        """Get the object from the api."""
        try:
            # by convention, we have a read-only user with the same name as the namespace.
            return self._api.core(user=self.namespace).read_namespaced_pod(self.name, self.namespace)
        except kubernetes.client.exceptions.ApiException as e:
            raise KubernetesApiError(f"Error from the kubernetes api: {e}") from e

    def refresh(self) -> None:
        """Refresh the api object from the kubernetes api server."""
        self._pod = self._get()

    def __str__(self) -> str:
        """String representation."""
        return f"Pod({self.namespace}/{self.name})"
