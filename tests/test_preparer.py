"""
How the agent sizes a job for the machine it runs on.
"""

from agent.preparer import capped_resources
from app.catalog.models import Resources

CLUSTER_NODE = Resources(cpus=16, memory_mb=4000, walltime_minutes=60, mpi=True)


def test_a_task_sized_for_a_node_gets_the_cpus_this_machine_gives():
    """
    A worker allowed four CPUs starts four MPI processes, not the
    sixteen a cluster node would give; the rest of the request stays.
    """
    capped = capped_resources(CLUSTER_NODE, 4)
    assert capped == CLUSTER_NODE.model_copy(update={"cpus": 4})


def test_without_a_limit_or_under_it_the_task_keeps_its_own_count():
    """
    No limit set (a cluster, where the scheduler decides) or a limit
    above the task's count: the request goes through unchanged.
    """
    assert capped_resources(CLUSTER_NODE, None) is CLUSTER_NODE
    assert capped_resources(CLUSTER_NODE, 32) is CLUSTER_NODE
