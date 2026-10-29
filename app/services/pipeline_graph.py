"""
Check a submitted pipeline's shape before anything is stored: at least
one node, each node id once, each edge between known nodes and given
once, and no cycle. Each problem is a 400 that names it.

Cycles are found with Kahn's algorithm: keep taking a node whose
parents have all been taken. Nodes never taken wait on each other, in
a cycle.
"""

from collections import Counter, deque
from collections.abc import Iterable

from app.api.errors import bad_request
from app.schemas.job import JobEdge, JobNode, PipelineSubmitRequest

EMPTY_MESSAGE = "Cannot submit empty pipeline; at least one node required."
CYCLE_MESSAGE = "Pipeline graph contains a cycle; must be a valid DAG."


def given_twice(names: Iterable[str]) -> list[str]:
    """
    The names that appear more than once, in the order first given.

    :param names: Node ids or edges.
    :type names: Iterable[str]
    :return: Each repeated name once.
    :rtype: list[str]
    """
    return [name for name, count in Counter(names).items() if count > 1]


def edge_name(edge: JobEdge) -> str:
    """
    How an edge is named in messages.

    :param edge: The edge.
    :type edge: JobEdge
    :return: ``parent -> child``.
    :rtype: str
    """
    return f"{edge.upstream_ui_id} -> {edge.downstream_ui_id}"


def check_nodes(nodes: list[JobNode]) -> None:
    """
    Refuse an empty pipeline, or one naming two nodes alike (edges name
    nodes by id, so the two could not be told apart).

    :param nodes: The submitted nodes.
    :type nodes: list[JobNode]
    :raises HTTPException: 400 naming the problem.
    """
    if not nodes:
        raise bad_request(EMPTY_MESSAGE)
    if twice := given_twice(node.ui_id for node in nodes):
        raise bad_request(f"Node ids given twice: {', '.join(twice)}")


def check_edges(nodes: list[JobNode], edges: list[JobEdge]) -> None:
    """
    Refuse an edge to or from an unknown node, or the same edge twice.

    :param nodes: The submitted nodes.
    :type nodes: list[JobNode]
    :param edges: The submitted edges.
    :type edges: list[JobEdge]
    :raises HTTPException: 400 naming the edge.
    """
    known = {node.ui_id for node in nodes}
    for edge in edges:
        if not {edge.upstream_ui_id, edge.downstream_ui_id} <= known:
            message = f"Edge references invalid node ID: {edge_name(edge)}"
            raise bad_request(message)
    if twice := given_twice(edge_name(edge) for edge in edges):
        raise bad_request(f"Edges given twice: {', '.join(twice)}")


def parent_counts(nodes: list[JobNode], edges: list[JobEdge]) -> dict[str, int]:
    """
    How many parents each node waits for.

    :param nodes: The nodes.
    :type nodes: list[JobNode]
    :param edges: The edges between them.
    :type edges: list[JobEdge]
    :return: Node id -> parents.
    :rtype: dict[str, int]
    """
    counts = dict.fromkeys((node.ui_id for node in nodes), 0)
    for edge in edges:
        counts[edge.downstream_ui_id] += 1
    return counts


def children_of(
    nodes: list[JobNode], edges: list[JobEdge]
) -> dict[str, list[str]]:
    """
    Each node's children.

    :param nodes: The nodes.
    :type nodes: list[JobNode]
    :param edges: The edges between them.
    :type edges: list[JobEdge]
    :return: Node id -> its children's ids.
    :rtype: dict[str, list[str]]
    """
    children: dict[str, list[str]] = {node.ui_id: [] for node in nodes}
    for edge in edges:
        children[edge.upstream_ui_id].append(edge.downstream_ui_id)
    return children


def check_acyclic(nodes: list[JobNode], edges: list[JobEdge]) -> None:
    """
    Refuse a pipeline with a cycle (Kahn's algorithm).

    :param nodes: The nodes, each id once.
    :type nodes: list[JobNode]
    :param edges: The edges between them, each once.
    :type edges: list[JobEdge]
    :raises HTTPException: 400 if some nodes wait on each other.
    """
    waiting = parent_counts(nodes, edges)
    children = children_of(nodes, edges)
    ready = deque(node for node, count in waiting.items() if count == 0)
    taken = 0
    while ready:
        taken += 1
        for child in children[ready.popleft()]:
            waiting[child] -= 1
            if waiting[child] == 0:
                ready.append(child)
    if taken != len(waiting):
        raise bad_request(CYCLE_MESSAGE)


def check_pipeline_graph(request: PipelineSubmitRequest) -> dict[str, int]:
    """
    Check a pipeline's shape, and say how many parents each node waits
    for.

    :param request: The submitted pipeline.
    :type request: PipelineSubmitRequest
    :return: Node id -> parents.
    :rtype: dict[str, int]
    :raises HTTPException: 400 naming the first problem found.
    """
    check_nodes(request.nodes)
    check_edges(request.nodes, request.edges)
    check_acyclic(request.nodes, request.edges)
    return parent_counts(request.nodes, request.edges)
