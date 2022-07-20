"""k8s module tests."""
from http import HTTPStatus
from unittest import mock

import kubernetes
import pytest
from kubernetes.client.models import V1Taint

from spicerack import k8s


def mock_list_value(val):
    """Helper for populate_mock."""
    if isinstance(val, dict):
        m = mock.MagicMock()
        populate_mock(m, val)
        return m
    # For non-objects we can just return the value.
    return val


def populate_mock(mocked, attrs):
    """Populates a mock with attributes and functions."""
    for name, value in attrs.items():
        target = getattr(mocked, name)
        if isinstance(value, dict):
            populate_mock(target, value)
        elif isinstance(value, list):
            setattr(mocked, name, [mock_list_value(v) for v in value])
        else:
            setattr(mocked, name, value)


class KubeTestBase:
    """Base class for testing all subclasses."""

    node_test_cases = {
        "schedulable": {"metadata": {"name": "node1"}, "spec": {"unschedulable": None, "taints": None}},
        "unschedulable": {"metadata": {"name": "node2"}, "spec": {"unschedulable": True, "taints": None}},
        "tainted": {
            "metadata": {"name": "node3"},
            "spec": {"unschedulable": None, "taints": [V1Taint(effect="NoExecute", key="dedicated", value="kask")]},
        },
    }
    pod_test_cases = {
        "orphaned": {
            "metadata": {"owner_references": None, "name": "foo", "namespace": "bar", "annotations": ["sigh"]},
            "status": {"phase": "Running"},
            "spec": {"termination_grace_period_seconds": 30},
        },
        "replicaset": {
            "metadata": {"owner_references": [{"kind": "ReplicaSet"}], "name": "foo", "namespace": "bar"},
            "status": {"phase": "Running"},
            "spec": {"termination_grace_period_seconds": 1},
        },
        "daemonset": {
            "metadata": {
                "owner_references": [{"kind": "DaemonSet"}, {"kind": "ReplicaSet"}],
                "name": "calico",
                "namespace": "bar",
            },
            "status": {"phase": "Running"},
            "spec": {"termination_grace_period_seconds": 30},
        },
        "finished": {
            "metadata": {
                "owner_references": [{"kind": "ReplicaSet"}],
                "name": "foo",
                "namespace": "bar",
            },
            "status": {"phase": "Succeeded"},
            "spec": {"termination_grace_period_seconds": 300},
        },
        "mirror": {
            "metadata": {
                "owner_references": [{"kind": "ReplicaSet"}],
                "name": "foo",
                "namespace": "bar",
                "annotations": ["kubernetes.io/config.mirror"],
            },
            "status": {"phase": "Running"},
        },
        "invalid_ref": {
            "metadata": {
                "owner_references": [],  # this should never happen, but better safe than sorry.
                "name": "foo",
                "namespace": "bar",
            },
            "status": {"phase": "Running"},
            "spec": {"termination_grace_period_seconds": 30},
        },
    }

    def setup_method(self):
        """Setup a mock api to work with."""
        # pylint: disable=attribute-defined-outside-init
        self._api = mock.MagicMock(spec=k8s.KubernetesApiFactory)
        self._coreapi = self._api.core.return_value

    def node_from_test_case(self, label):
        """Get an api node object from a test label."""
        return self._get_from_test_case("node", label)

    def pod_from_test_case(self, label):
        """Get an api pod object from a test label."""
        return self._get_from_test_case("pod", label)

    def _get_from_test_case(self, what, label):
        if what == "pod":
            cases = self.pod_test_cases
            cls = kubernetes.client.models.v1_pod.V1Pod
        elif what == "node":
            cases = self.node_test_cases
            cls = kubernetes.client.models.v1_node.V1Node
        else:
            raise ValueError(f"no test cases for '{what}'")

        try:
            attrs = cases[label]
        except KeyError:
            return None
        obj = mock.MagicMock(spec=cls)
        populate_mock(obj, attrs)
        return obj


class TestKubernetes(KubeTestBase):
    """Test the kubernetes object that is wired into spicerack eventually."""

    @pytest.fixture
    def kube(self):
        """Fixture to get a test object."""
        k = k8s.Kubernetes("group", "cluster", dry_run=False)
        k.api = self._api
        return k

    @staticmethod
    def test_initialize_api():
        """Values are passed to the api correctly."""
        k = k8s.Kubernetes("group", "cluster")
        assert k.api.cluster == "cluster"

    @staticmethod
    def test_initialize_dry_run(kube):
        """Dry run is initialized correctly."""
        assert kube.dry_run is False
        assert k8s.Kubernetes("group", "cluster", dry_run=True).dry_run is True

    def test_get_node(self, kube):
        """Getting a node works."""
        list_node = mock.MagicMock()
        list_node.items = [self.node_from_test_case("schedulable")]
        self._coreapi.list_node.return_value = list_node
        node = kube.get_node("node1")
        assert node.name == "node1"
        self._coreapi.list_node.assert_called_with(field_selector="metadata.name=node1")

    def test_get_pod(self, kube):
        """Getting a pod works."""
        with mock.patch("spicerack.k8s.KubernetesNode._get") as mocked:
            mocked.return_value = self.pod_from_test_case("replicaset")
            pod = kube.get_pod("bar", "foo")
            assert pod.name == "foo"
            assert pod.is_terminated() is False


class TestKubernetesApiFactory:
    """Test the api factory class."""

    def setup_method(self):
        """Setup a mock api to work with."""
        # pylint: disable=attribute-defined-outside-init
        self._api = k8s.KubernetesApiFactory("cluster")

    @mock.patch("kubernetes.config.load_kube_config")
    def test_configuration(self, mocked):
        """The configuration is correctly loaded."""
        my_config = kubernetes.client.Configuration()

        with mock.patch("kubernetes.client.Configuration") as conf:
            conf.return_value = my_config
            assert self._api.configuration("cpt_harlock") == my_config
            conf.assert_called()
            mocked.assert_called_with(
                config_file="/etc/kubernetes/cpt_harlock-cluster.config", client_configuration=my_config
            )

    @mock.patch("kubernetes.config.load_kube_config")
    def test_config_cached(self, mocked):
        """A configuration gets only loaded once."""
        self._api.configuration("cpt_harlock")
        self._api.configuration("cpt_harlock")
        assert mocked.call_count == 1

    def test_config_invalid_user(self):
        """An invalid user will raise an exception."""
        with pytest.raises(k8s.KubernetesError):
            self._api.configuration("../../etc/passwd")

    @mock.patch("kubernetes.config.load_kube_config")
    def test_config_bad_config(self, mocked):
        """An invalid or inexistent file will cause an exception."""
        mocked.side_effect = kubernetes.config.config_exception.ConfigException("Arcadia!")
        with pytest.raises(k8s.KubernetesError):
            self._api.configuration("cpt_harlock")

    def test_core(self):
        """Get the core api interface."""
        self._api.configuration = mock.MagicMock(return_value=kubernetes.client.Configuration())
        assert isinstance(self._api.core(), kubernetes.client.CoreV1Api)


class TestKubernetesNode(KubeTestBase):
    """Test the KubernetesNode class."""

    @pytest.fixture
    def node(self, label):
        """Returns a node from the test cases."""
        _node = self.node_from_test_case(label)
        if _node is None:
            fqdn = None
        else:
            fqdn = _node.metadata.name
        return k8s.KubernetesNode(fqdn, self._api, dry_run=False, init_obj=_node)

    @pytest.fixture
    def dry_run(self, label):
        """Returns a node, dry-run set to true."""
        _n = self.node_from_test_case(label)
        self._coreapi.list_node.return_value = self.list_nodes(_n.metadata.name)
        k = k8s.Kubernetes("group", "cluster", dry_run=True)
        k.api = self._api
        return k.get_node(_n.metadata.name)

    def list_nodes(self, name):
        """Returns a node list."""
        items = []
        for label in self.node_test_cases:
            n = self.node_from_test_case(label)
            n.metadata.annotations = ["refreshed"]
            if n.metadata.name == name:
                items.append(n)
        m = mock.MagicMock()
        m.items = items
        return m

    def test_bad_init(self):
        """A bad initial object will cause an exception."""
        n = self.node_from_test_case("schedulable")
        with pytest.raises(k8s.KubernetesError):
            k8s.KubernetesNode("fqdn", self._api, init_obj=n)

    @staticmethod
    @pytest.mark.parametrize("label,expected", [("schedulable", True), ("unschedulable", False)])
    def test_is_schedulable(node, expected):
        """Is the node schedulable or not."""
        assert node.is_schedulable() is expected

    @staticmethod
    @pytest.mark.parametrize("label,expected", [("schedulable", "node1"), ("unschedulable", "node2")])
    def test_name(node, expected):
        """Test fetching the node name."""
        assert node.name == expected

    @pytest.mark.parametrize("label,has_calls", [("schedulable", True), ("unschedulable", False)])
    def test_cordon(self, node, has_calls):
        """Cordoning a schedulable node works."""
        patch_expected = self.node_from_test_case("schedulable")
        patch_expected.spec.unschedulable = True
        self._coreapi.patch_node.return_value = patch_expected
        # Happy path, will not raise exception.
        node.cordon()
        if has_calls:
            # Check the call to the api is what we expect.
            self._coreapi.patch_node.assert_called_with("node1", {"spec": {"unschedulable": True}})
        else:
            self._coreapi.patch_node.assert_not_called()
        assert node.is_schedulable() is False

    @pytest.mark.parametrize("label", ["schedulable"])
    def test_cordon_failed(self, node):
        """If cordoning doesn't work, we raise an exception."""
        # If the node is still schedulable after the cordoning, raise a check error
        self._coreapi.patch_node.return_value = self.node_from_test_case("schedulable")
        with pytest.raises(k8s.KubernetesCheckError):
            node.cordon()
        # If the api returns an error, raise an api error
        self._coreapi.patch_node.side_effect = kubernetes.client.exceptions.ApiException("test")
        with pytest.raises(k8s.KubernetesApiError):
            node.cordon()

    @pytest.mark.parametrize("label", ["schedulable"])
    def test_cordon_dry_run(self, dry_run):
        """Cordon in dry run doesn't actually modify the node."""
        dry_run.cordon()
        self._coreapi.patch_node.assert_not_called()

    @pytest.mark.parametrize("label,has_calls", [("schedulable", False), ("unschedulable", True)])
    def test_uncordon(self, node, has_calls):
        """Cordoning a schedulable node works."""
        patch_expected = self.node_from_test_case("schedulable")
        patch_expected.spec.unschedulable = False
        self._coreapi.patch_node.return_value = patch_expected
        # Happy path, will not raise exception.
        node.uncordon()
        if has_calls:
            # Check the call to the api is what we expect.
            self._coreapi.patch_node.assert_called_with("node2", {"spec": {"unschedulable": False}})
        else:
            self._coreapi.patch_node.assert_not_called()
        assert node.is_schedulable() is True

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_uncordon_failed(self, node):
        """If uncordoning doesn't work, we raise an exception."""
        # If the node is still schedulable after the cordoning, raise a check error
        self._coreapi.patch_node.return_value = self.node_from_test_case("unschedulable")
        with pytest.raises(k8s.KubernetesCheckError):
            node.uncordon()
        # If the api returns an error, raise an api error
        self._coreapi.patch_node.side_effect = kubernetes.client.exceptions.ApiException("test")
        with pytest.raises(k8s.KubernetesApiError):
            node.uncordon()

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_uncordon_dry_run(self, dry_run):
        """Cordon in dry run doesn't actually modify the node."""
        dry_run.uncordon()
        self._coreapi.patch_node.assert_not_called()

    @pytest.mark.parametrize("label", ["schedulable"])
    def test_refresh(self, node):
        """Refreshing data works."""
        # Non-empty list
        self._coreapi.list_node.return_value = self.list_nodes("node1")
        node.refresh()
        assert "refreshed" in node._node.metadata.annotations  # pylint: disable=protected-access

    @pytest.mark.parametrize("label", ["schedulable"])
    def test_refresh_multiple_find(self, node):
        """Refreshing fails if list_node returns multiple results."""
        response = self.list_nodes("node1")
        response.items.append(self.node_from_test_case("unschedulable"))
        self._coreapi.list_node.return_value = response
        with pytest.raises(k8s.KubernetesError):
            node.refresh()

    @pytest.mark.parametrize("label", ["schedulable"])
    def test_refresh_not_found(self, node):
        """Refreshing raises an error if the node has disappeared."""
        self._coreapi.list_node.return_value = self.list_nodes("pinkunicorn")
        with pytest.raises(k8s.KubernetesError):
            node.refresh()
        self._coreapi.list_node.side_effect = kubernetes.client.exceptions.ApiException("test")
        with pytest.raises(k8s.KubernetesApiError):
            node.refresh()

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_drain(self, mocked_wmflib_sleep, node):
        """A successful drain works as expected."""
        before_drain = mock.MagicMock()
        before_drain.items = [self.pod_from_test_case(label) for label in ["replicaset", "daemonset"]]
        # After draining, we expect the remaining pods to just be the unevictable ones.
        after_drain = mock.MagicMock()
        after_drain.items = [self.pod_from_test_case(label) for label in ["daemonset"]]
        self._coreapi.list_pod_for_all_namespaces.side_effect = [before_drain, after_drain]
        # no exception raised.
        with mock.patch("spicerack.k8s.time.sleep") as sl:
            node.drain()
            sl.assert_not_called()
        assert self._coreapi.create_namespaced_pod_eviction.call_count == 1
        assert self._coreapi.list_pod_for_all_namespaces.call_count == 2
        # no retries
        mocked_wmflib_sleep.assert_not_called()

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_drain_eventually_successful(self, node):
        """Test that retrying can eventually succeed."""
        before_drain = mock.MagicMock()
        before_drain.items = [self.pod_from_test_case(label) for label in ["replicaset", "daemonset"]]
        # After draining, we expect the remaining pods to just be the unevictable ones.
        after_drain = mock.MagicMock()
        after_drain.items = [self.pod_from_test_case(label) for label in ["daemonset"]]
        self._coreapi.list_pod_for_all_namespaces.side_effect = [before_drain, before_drain, before_drain, after_drain]
        with mock.patch("spicerack.k8s.time.sleep") as sl:
            node.drain()
            # expect sleep to be called once for max_grace_period (30s) and once from @retry (3s)
            assert sl.call_args_list == [((30,),), ((3,),)]

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_drain_leftover(self, node):
        """If there are leftover pods an exception is raised."""
        # Now assume we weren't able to evict anything
        before_drain = mock.MagicMock()
        before_drain.items = [self.pod_from_test_case(label) for label in ["replicaset", "daemonset"]]
        self._coreapi.list_pod_for_all_namespaces.return_value = before_drain
        with pytest.raises(k8s.KubernetesCheckError, match="still has 2 pods"):
            with mock.patch("spicerack.k8s.time.sleep", return_value=None) as sl:
                node.drain()
                sl.assert_called_once_with(1)

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_drain_failed(self, node):
        """Test draining when a pod doesn't evict."""
        # Patch get_pods to return a pod that will fail to evict
        pod_with_no_eviction = k8s.KubernetesPod(
            "bar", "foo", self._api, dry_run=False, init_obj=self.pod_from_test_case("replicaset")
        )
        pod_with_no_eviction.evict = mock.MagicMock(side_effect=k8s.KubernetesApiError("fail!"))
        node.get_pods = mock.MagicMock(return_value=[pod_with_no_eviction])

        with pytest.raises(k8s.KubernetesCheckError, match="Could not evict all pods"):
            node.drain()

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_drain_dry_run(self, dry_run):
        """Draining with dry_run does nothing."""
        before_drain = mock.MagicMock()
        before_drain.items = [self.pod_from_test_case(label) for label in ["finished", "replicaset", "daemonset"]]
        # we're not actually draining, so the return value will always be the same.
        self._coreapi.list_pod_for_all_namespaces.return_value = before_drain
        with mock.patch("spicerack.k8s.time.sleep", return_value=None):
            dry_run.drain()
        self._coreapi.create_namespaced_pod_eviction.assert_not_called()

    @pytest.mark.parametrize("label", ["unschedulable"])
    def test_drain_api_error(self, node):
        """Draining with an api error will raise an exception."""
        self._coreapi.list_pod_for_all_namespaces.side_effect = kubernetes.client.exceptions.ApiException("test")
        with pytest.raises(k8s.KubernetesApiError):
            node.drain()
        self._coreapi.list_pod_for_all_namespaces.assert_called_with(field_selector="spec.nodeName=node2")

    @staticmethod
    @pytest.mark.parametrize(
        "label,expected",
        [("schedulable", []), ("tainted", [V1Taint(effect="NoExecute", key="dedicated", value="kask")])],
    )
    def test_taints(node, expected):
        """Test fetching taints."""
        assert node.taints == expected


class TestKubernetesPod(KubeTestBase):
    """Unit testing KubernetesPod."""

    @pytest.fixture
    def pod(self, label):
        """Obtain a test pod."""
        _pod = self.pod_from_test_case(label)
        if _pod is None:
            name = "foo"
            ns = "bar"
        else:
            name = _pod.metadata.name
            ns = _pod.metadata.namespace

        return k8s.KubernetesPod(ns, name, self._api, dry_run=False, init_obj=_pod)

    @staticmethod
    @pytest.mark.parametrize("label,expected", [("orphaned", None), ("invalid_ref", None), ("daemonset", "DaemonSet")])
    def test_controller(pod, expected):
        """The output of pod.controller."""
        if expected is None:
            assert pod.controller is None
        else:
            assert pod.controller.kind == expected

    @staticmethod
    @pytest.mark.parametrize("label, expected", [("daemonset", True), ("replicaset", False), ("invalid_ref", False)])
    def test_is_daemonset(pod, expected):
        """Detecting a daemonset."""
        assert pod.is_daemonset() is expected

    @staticmethod
    @pytest.mark.parametrize("label, expected", [("finished", True), ("replicaset", False), ("invalid_ref", False)])
    def test_is_terminated(pod, expected):
        """Detecting a terminated pod."""
        assert pod.is_terminated() is expected

    @staticmethod
    @pytest.mark.parametrize("label, expected", [("mirror", True), ("orphaned", False)])
    def test_is_mirror(pod, expected):
        """Detecting mirror pods."""
        assert pod.is_mirror() is expected

    @staticmethod
    @pytest.mark.parametrize(
        "label,expected",
        [("daemonset", False), ("replicaset", True), ("orphaned", False), ("finished", True), ("mirror", False)],
    )
    def test_is_evictable(pod, expected):
        """Is the pod evictable."""
        assert pod.is_evictable() is expected

    @pytest.mark.parametrize("label", ["no data"])
    def test_refresh(self, pod):
        """The requests to the api for the pod."""
        self._coreapi.read_namespaced_pod.assert_called_with("foo", "bar")
        self._api.core.assert_called_with(user="bar")
        refresher = self.pod_from_test_case("replicaset")
        self._coreapi.read_namespaced_pod.return_value = refresher
        pod.refresh()
        # Without the refresh this would fail.
        assert pod.is_evictable()
        self._coreapi.read_namespaced_pod.side_effect = kubernetes.client.exceptions.ApiException("test")
        with pytest.raises(k8s.KubernetesApiError):
            pod.refresh()

    def test_bad_init(self):
        """Test discrepancy between init object and parameters."""
        init_obj = self.pod_from_test_case("daemonset")
        with pytest.raises(k8s.KubernetesError):
            k8s.KubernetesPod("bar", "name", self._api, init_obj=init_obj)
        with pytest.raises(k8s.KubernetesError):
            k8s.KubernetesPod("namespace", "calico", self._api, init_obj=init_obj)

    def test_evict(self):
        """Evicting a pod calls the api."""
        k8s.KubernetesPod(
            "bar", "foo", self._api, init_obj=self.pod_from_test_case("replicaset"), dry_run=False
        ).evict()
        self._coreapi.create_namespaced_pod_eviction.assert_called()

    def test_evict_unevictable(self):
        """Evicting an unevictable pod raises an exception."""
        with pytest.raises(k8s.KubernetesError):
            k8s.KubernetesPod(
                "bar", "calico", self._api, init_obj=self.pod_from_test_case("daemonset"), dry_run=False
            ).evict()

    def test_evict_error(self):
        """When a pod eviction returns an error, an api error is raised."""
        self._coreapi.create_namespaced_pod_eviction.side_effect = kubernetes.client.exceptions.ApiException("test")
        with pytest.raises(k8s.KubernetesApiError):
            k8s.KubernetesPod(
                "bar", "foo", self._api, init_obj=self.pod_from_test_case("replicaset"), dry_run=False
            ).evict()
        # Also test dry run. It won't raise an exception
        k8s.KubernetesPod("bar", "foo", self._api, init_obj=self.pod_from_test_case("replicaset")).evict()

    @mock.patch("wmflib.decorators.time.sleep", return_value=None)
    def test_evict_retry(self, mocked_wmflib_sleep):
        """When a pod eviction returns 429, retry."""
        self._coreapi.create_namespaced_pod_eviction.side_effect = kubernetes.client.exceptions.ApiException(
            status=HTTPStatus.TOO_MANY_REQUESTS, reason="test"
        )
        with pytest.raises(k8s.KubernetesApiTooManyRequests):
            k8s.KubernetesPod(
                "bar", "foo", self._api, init_obj=self.pod_from_test_case("replicaset"), dry_run=False
            ).evict()
        # Check if eviction has been retried
        assert self._coreapi.create_namespaced_pod_eviction.call_count == 4
        assert mocked_wmflib_sleep.call_count == 3
        # Also test dry run. It won't raise an exception
        k8s.KubernetesPod("bar", "foo", self._api, init_obj=self.pod_from_test_case("replicaset")).evict()
