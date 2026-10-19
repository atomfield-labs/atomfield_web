import { useState, useEffect, useCallback, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useReactFlow,
  type Node,
  type Edge,
  applyNodeChanges,
  applyEdgeChanges,
  reconnectEdge,
  Position,
  NodeToolbar,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { v4 as uuidv4 } from 'uuid';
import { GitBranch } from 'lucide-react';
import RemovableEdge from './RemovableEdge';
import StructureNode from './StructureNode';
import CalculationNode from './CalculationNode';
import BranchExpanderNode from './BranchExpanderNode';
import BranchCircleNode from './BranchCircleNode';
import BranchDotsNode from './BranchDotsNode';
import ResultViewerNode from './ResultViewerNode';
import { parseStructureFile } from '../../utils/structureParser';

const edgeTypes = {
  removable: RemovableEdge,
};

const nodeTypes: any = {
  default: CalculationNode,
  structure: StructureNode,
  branchExpander: BranchExpanderNode,
  branchCircle: BranchCircleNode,
  branchDots: BranchDotsNode,
  resultViewer: ResultViewerNode,
};

interface GraphCanvasProps {
  blueprint: { nodes: any[]; edges: any[] };
  onNodeClick?: (node: any) => void;
  onNodeDoubleClick?: (node: any) => void;
  selectedNodeId?: string | null;
  isEditable?: boolean;
  sessionId?: string;
  showResultsNode?: boolean;
  onOpenResults?: () => void;
  onRegisterDeleteHandler?: (handler: (nodeId: string) => void) => void;
  onRegisterUpdateParamsHandler?: (handler: (nodeId: string, newParams: Record<string, any>) => void) => void;
  onRegisterUpdateExecutionHandler?: (handler: (nodeId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => void) => void;
  onRegisterReplicateHandler?: (handler: (nodeId: string, count: number) => void) => void;
  onNodesDelete?: (deleted: Node[]) => void;
  onGraphChange?: (graph: { nodes: Node[]; edges: Edge[] }) => void;
}

const statusColors: Record<string, string> = {
  Draft: '#f8fafc',
  Ready: '#f8fafc',
  Blocked: '#cbd5e1',
  Pending: '#fde047',
  Running: '#60a5fa',
  Success: '#4ade80',
  Failed: '#f87171'
};

function isGroupMemberNode(node?: Node | null, targetGroupId?: string, parentId?: string): boolean {
  if (!node || !targetGroupId) return false;
  if (parentId && node.id === parentId) return false;
  const nodeData = (node.data || {}) as any;
  return (
    nodeData.branchGroupId === targetGroupId ||
    nodeData.groupId === targetGroupId ||
    node.id === `expander-up-${targetGroupId}` ||
    node.id === `expander-down-${targetGroupId}` ||
    ((node.type === 'branchDots' || node.type === 'branchExpander') &&
      (nodeData.groupId === targetGroupId || nodeData.branchGroupId === targetGroupId))
  );
}

export default function GraphCanvas({ 
  blueprint, 
  onNodeClick, 
  onNodeDoubleClick,
  selectedNodeId: _selectedNodeId,
  isEditable = false,
  sessionId: _sessionId,
  showResultsNode = false,
  onOpenResults,
  onRegisterDeleteHandler,
  onRegisterUpdateParamsHandler,
  onRegisterUpdateExecutionHandler,
  onRegisterReplicateHandler,
  onNodesDelete,
  onGraphChange,
}: GraphCanvasProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [clickedNodeId, setClickedNodeId] = useState<string | null>(null);
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [customToolbarCount, setCustomToolbarCount] = useState(3);

  const activeToolbarNodeId = clickedNodeId;

  const nodesRef = useRef<Node[]>(nodes);
  const edgesRef = useRef<Edge[]>(edges);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    return () => {
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!clickedNodeId) return;

    const handleGlobalPointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target) return;

      if (
        target.closest('.react-flow__node-toolbar') ||
        target.closest('[data-toolbar="true"]')
      ) {
        return;
      }

      if (target.closest(`[data-id="${clickedNodeId}"]`)) {
        return;
      }

      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      setClickedNodeId(null);
    };

    window.addEventListener('pointerdown', handleGlobalPointerDown, true);
    return () => {
      window.removeEventListener('pointerdown', handleGlobalPointerDown, true);
    };
  }, [clickedNodeId]);

  useEffect(() => {
    if (activeToolbarNodeId) {
      const activeNode = nodes.find((n) => n.id === activeToolbarNodeId);
      const cnt =
        (activeNode?.data as any)?.branchCount ||
        ((activeNode?.data as any)?.branchGroupId
          ? nodes.filter(
              (n) =>
                n.type === 'branchCircle' &&
                (n.data as any)?.branchGroupId &&
                (n.data as any)?.branchGroupId === (activeNode?.data as any)?.branchGroupId
            ).length + 1
          : 3);
      setCustomToolbarCount(cnt > 1 ? cnt : 3);
    }
  }, [activeToolbarNodeId, nodes]);

  const { screenToFlowPosition, fitView: rfFitView } = useReactFlow();

  useEffect(() => {
    if (onGraphChange) {
      onGraphChange({ nodes, edges });
    }
  }, [nodes, edges, onGraphChange]);

  const processStructureFile = useCallback(async (file: File, targetNodeId?: string, dropPosition?: { x: number; y: number }) => {
    try {
      const text = await file.text();
      const parsed = parseStructureFile(file.name, text);
      const workspacePath = `/workspace/${file.name}`;

      let nodeId = targetNodeId;
      if (!nodeId) {
        nodeId = uuidv4();
        const initialNode: Node = {
          id: nodeId,
          type: 'structure',
          position: dropPosition || { x: 100, y: 150 },
          sourcePosition: Position.Right,
          data: {
            ...parsed,
            raw_content: text,
            workspace_path: workspacePath,
            onFileUpload: (nId: string, f: File) => processStructureFile(f, nId),
          }
        };
        setNodes((nds) => nds.concat(initialNode));
      } else {
        setNodes((nds) => nds.map(n => n.id === nodeId ? {
          ...n,
          data: {
            ...n.data,
            ...parsed,
            raw_content: text,
            workspace_path: workspacePath,
            onFileUpload: (nId: string, f: File) => processStructureFile(f, nId),
          }
        } : n));
      }
    } catch (err: any) {
      console.error("Failed to parse structure file in browser", err);
    }
  }, []);

  const updateNodeParameters = useCallback((nodeId: string, newParams: Record<string, any>) => {
    setNodes((nds) =>
      nds.map((n) => {
        const nodeData = n.data as any;
        if (n.id === nodeId || nodeData?.originalData?.ui_id === nodeId) {
          const updatedOriginal = nodeData?.originalData
            ? { ...nodeData.originalData, parameters: newParams }
            : undefined;
          return {
            ...n,
            data: {
              ...n.data,
              parameters: newParams,
              originalData: updatedOriginal
            }
          };
        }
        return n;
      })
    );
  }, []);

  const updateNodeExecution = useCallback((nodeId: string, status: string, logs?: string, artifacts?: string[], jobId?: string) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (
          n.id === nodeId ||
          (n.data as any)?.script_id === nodeId ||
          (n.data as any)?.originalData?.ui_id === nodeId ||
          (n.data as any)?.originalData?.id === nodeId
        ) {
          const bg = statusColors[status] || '#f8fafc';
          const border = status === 'Running' ? '2px solid #3b82f6' : status === 'Success' ? '2px solid #22c55e' : status === 'Failed' ? '2px solid #ef4444' : '2px solid #94a3b8';
          return {
            ...n,
            data: {
              ...(n.data as any),
              status,
              logs: logs !== undefined ? logs : (n.data as any)?.logs,
              artifacts: artifacts !== undefined ? artifacts : (n.data as any)?.artifacts,
              job_id: jobId || (n.data as any)?.job_id,
            },
            style: {
              ...(n.style || {}),
              background: bg,
              border: border,
            }
          };
        }
        return n;
      })
    );
  }, []);

  useEffect(() => {
    if (onRegisterUpdateParamsHandler) {
      onRegisterUpdateParamsHandler(updateNodeParameters);
    }
  }, [updateNodeParameters, onRegisterUpdateParamsHandler]);

  useEffect(() => {
    if (onRegisterUpdateExecutionHandler) {
      onRegisterUpdateExecutionHandler(updateNodeExecution);
    }
  }, [updateNodeExecution, onRegisterUpdateExecutionHandler]);

  const expandSideRef = useRef<(groupId: string, side: 'up' | 'down') => void>(() => {});
  const collapseSideRef = useRef<(groupId: string, side: 'up' | 'down') => void>(() => {});

  const expandSide = useCallback((groupId: string, side: 'up' | 'down') => {
    setNodes((currentNodes) => {
      const expander = currentNodes.find(
        (n) => n.type === 'branchDots' && n.data?.groupId === groupId && n.data?.side === side
      );
      if (!expander) return currentNodes;

      const intermediateNodeIds: string[] = (expander.data?.intermediateNodeIds as string[]) || [];
      const parentNode = currentNodes.find(
        (n) => n.id === groupId || ((n.data as any)?.branchGroupId === groupId && (n.data as any)?.isParentBranch)
      );
      const x0 = parentNode ? parentNode.position.x : expander.position.x - 82;
      const y0 = parentNode ? parentNode.position.y : 0;

      const hiddenList = intermediateNodeIds.filter(
        (id) => currentNodes.find((n) => n.id === id)?.hidden !== false
      );
      if (hiddenList.length === 0) return currentNodes;

      const batchSize = (expander.data?.batchSize as number) || 5;
      const unhideNow = hiddenList.slice(0, batchSize);
      const unhideSet = new Set(unhideNow);

      setEdges((currentEdges) =>
        currentEdges.map((e) =>
          unhideSet.has(e.target) || unhideSet.has(e.source) ? { ...e, hidden: false } : e
        )
      );

      const newlyVisibleCount = unhideNow.length;
      const previouslyVisibleCount = intermediateNodeIds.length - hiddenList.length;
      const totalVisibleCount = previouslyVisibleCount + newlyVisibleCount;
      const remainingHidden = hiddenList.length - newlyVisibleCount;
      const isFullyExpanded = remainingHidden === 0;

      const boundaryNodeId = expander.data?.boundaryNodeId as string;

      return currentNodes.map((n) => {
        if (intermediateNodeIds.includes(n.id)) {
          const isNowVisible = !hiddenList.includes(n.id) || unhideSet.has(n.id);
          if (isNowVisible) {
            const visibleIdx = intermediateNodeIds
              .filter((id) => !hiddenList.includes(id) || unhideSet.has(id))
              .indexOf(n.id);

            const yPos =
              side === 'up'
                ? y0 - 46 - (visibleIdx + 1) * 46
                : y0 + 82 + (visibleIdx + 1) * 46;

            return {
              ...n,
              hidden: false,
              position: { x: x0 + 82, y: yPos },
            };
          } else {
            return {
              ...n,
              hidden: true,
            };
          }
        }

        if (n.id === expander.id) {
          const yPos =
            side === 'up'
              ? y0 - 46 - (totalVisibleCount + 1) * 46
              : y0 + 82 + (totalVisibleCount + 1) * 46;

          return {
            ...n,
            position: { x: x0 + 82, y: yPos },
            data: {
              ...n.data,
              hiddenCount: remainingHidden,
              isFullyExpanded,
              onExpandSide: (g: string, s: 'up' | 'down') => expandSideRef.current(g, s),
              onCollapseSide: (g: string, s: 'up' | 'down') => collapseSideRef.current(g, s),
            },
          };
        }

        if (n.id === boundaryNodeId) {
          const yPos =
            side === 'up'
              ? y0 - 46 - (totalVisibleCount + 2) * 46
              : y0 + 82 + (totalVisibleCount + 2) * 46;

          return {
            ...n,
            position: { x: x0 + 82, y: yPos },
          };
        }

        return n;
      });
    });
  }, []);

  const collapseSide = useCallback((groupId: string, side: 'up' | 'down') => {
    setNodes((currentNodes) => {
      const expander = currentNodes.find(
        (n) => n.type === 'branchDots' && n.data?.groupId === groupId && n.data?.side === side
      );
      if (!expander) return currentNodes;

      const intermediateNodeIds: string[] = (expander.data?.intermediateNodeIds as string[]) || [];
      const intermediateSet = new Set(intermediateNodeIds);

      const parentNode = currentNodes.find(
        (n) => n.id === groupId || ((n.data as any)?.branchGroupId === groupId && (n.data as any)?.isParentBranch)
      );
      const x0 = parentNode ? parentNode.position.x : expander.position.x - 82;
      const y0 = parentNode ? parentNode.position.y : 0;

      setEdges((currentEdges) =>
        currentEdges.map((e) =>
          intermediateSet.has(e.target) || intermediateSet.has(e.source) ? { ...e, hidden: true } : e
        )
      );

      const boundaryNodeId = expander.data?.boundaryNodeId as string;

      return currentNodes.map((n) => {
        if (intermediateSet.has(n.id)) {
          return {
            ...n,
            hidden: true,
          };
        }

        if (n.id === expander.id) {
          const yPos = side === 'up' ? y0 - 92 : y0 + 128;
          return {
            ...n,
            position: { x: x0 + 82, y: yPos },
            data: {
              ...n.data,
              hiddenCount: intermediateNodeIds.length,
              isFullyExpanded: false,
              onExpandSide: (g: string, s: 'up' | 'down') => expandSideRef.current(g, s),
              onCollapseSide: (g: string, s: 'up' | 'down') => collapseSideRef.current(g, s),
            },
          };
        }

        if (n.id === boundaryNodeId) {
          const yPos = side === 'up' ? y0 - 138 : y0 + 174;
          return {
            ...n,
            position: { x: x0 + 82, y: yPos },
          };
        }

        return n;
      });
    });
  }, []);

  useEffect(() => {
    expandSideRef.current = expandSide;
    collapseSideRef.current = collapseSide;
  }, [expandSide, collapseSide]);

  const setParallelCount = useCallback((targetNodeId: string, targetCount: number) => {
    if (targetCount < 1) targetCount = 1;
    const currentNodes = nodesRef.current;
    const currentEdges = edgesRef.current;

    const targetNode = currentNodes.find(
      (n) => n.id === targetNodeId || (n.data as any)?.originalData?.ui_id === targetNodeId
    );
    if (!targetNode) return;

    const targetData = (targetNode.data || {}) as any;
    const groupId = targetData.branchGroupId || targetNode.id;

    // Find the parent node (the center calculation card)
    const parentNode = currentNodes.find(
      (n) => n.id === groupId || (n.data as any)?.originalData?.ui_id === groupId || (n.data as any)?.isParentBranch
    ) || targetNode;

    const parentData = (parentNode.data || {}) as any;
    const baseLabel = parentData.cleanLabel || parentData.label || parentData.script_name || 'Calculation';
    const cleanBase = typeof baseLabel === 'string'
      ? baseLabel.replace(/\s*\((?:Branch\s*\d+|#\d+)\)$/i, '').replace(/\s+#\d+$/, '')
      : 'Calculation';

    const x0 = parentNode.position.x;
    const y0 = parentNode.position.y;

    const groupMemberIds = new Set(
      currentNodes
        .filter((n) => n.id === parentNode.id || isGroupMemberNode(n, groupId, parentNode.id))
        .map((n) => n.id)
    );

    const externalIncomingSources = Array.from(
      new Set(
        currentEdges
          .filter((e) => groupMemberIds.has(e.target) && !groupMemberIds.has(e.source))
          .map((e) => e.source)
      )
    );

    const externalOutgoingTargets = Array.from(
      new Set(
        currentEdges
          .filter((e) => groupMemberIds.has(e.source) && !groupMemberIds.has(e.target))
          .map((e) => e.target)
      )
    );

    // Existing replicas belonging to this group (excluding the parent and expanders)
    const existingReplicas = currentNodes.filter(
      (n) => n.id !== parentNode.id && (n.data as any)?.branchGroupId === groupId && n.type === 'branchCircle'
    );

    // If targetCount is 1: Reset to single parent node, remove all replicas and expanders
    if (targetCount <= 1) {
      const groupOtherIds = new Set(
        currentNodes
          .filter((n) => isGroupMemberNode(n, groupId, parentNode.id))
          .map((n) => n.id)
      );
      const nextNodes = currentNodes
        .filter((n) => !groupOtherIds.has(n.id))
        .map((n) => {
          if (n.id === parentNode.id) {
            return {
              ...n,
              data: {
                ...n.data,
                cleanLabel: cleanBase,
                label: cleanBase,
                branchGroupId: undefined,
                branchCount: 1,
                isParentBranch: false,
              },
            };
          }
          return n;
        });

      const nextEdges = currentEdges.filter((e) => !groupOtherIds.has(e.target) && !groupOtherIds.has(e.source));

      setNodes(nextNodes);
      setEdges(nextEdges);
      if (onGraphChange) onGraphChange({ nodes: nextNodes, edges: nextEdges });
      return;
    }

    // Target count > 1:
    const neededReplicas = targetCount - 1;
    let keptReplicas: Node[] = [];
    let nextEdges = [...currentEdges];

    if (existingReplicas.length >= neededReplicas) {
      // Reduce replicas (e.g. from 100 to 10)
      keptReplicas = existingReplicas.slice(0, neededReplicas);
      const toRemove = existingReplicas.slice(neededReplicas);
      const toRemoveIds = new Set(toRemove.map((r) => r.id));
      nextEdges = nextEdges.filter((e) => !toRemoveIds.has(e.target) && !toRemoveIds.has(e.source));
    } else {
      // Expand replicas (e.g. from 2 to 10)
      keptReplicas = [...existingReplicas];
      const countToAdd = neededReplicas - existingReplicas.length;

      for (let k = 0; k < countToAdd; k++) {
        const newId = uuidv4();
        const clonedParams = JSON.parse(
          JSON.stringify(parentData.parameters || {})
        );
        const clonedDefaults = JSON.parse(
          JSON.stringify(parentData.default_parameters || clonedParams)
        );

        const newReplica: Node = {
          id: newId,
          type: 'branchCircle',
          position: { x: x0 + 82, y: y0 },
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          data: {
            ...parentData,
            label: cleanBase,
            cleanLabel: cleanBase,
            filename: parentData.filename || parentData.script_name,
            script_id: newId,
            ui_id: newId,
            status: 'Draft',
            parameters: clonedParams,
            default_parameters: clonedDefaults,
            branchGroupId: groupId,
            originalData: {
              ui_id: newId,
              script_name: parentData.filename || parentData.script_name,
              parameters: clonedParams,
              default_parameters: clonedDefaults,
              label: cleanBase,
              status: 'Draft',
            },
          },
        };

        externalIncomingSources.forEach((sourceId) => {
          const edgeId = `e-${sourceId}-${newId}`;
          nextEdges.push({
            id: edgeId,
            source: sourceId,
            target: newId,
            type: 'removable',
            animated: true,
            style: { stroke: '#64748b', strokeWidth: 2 },
          });

          if (
            (parentData as any)?.structureFilename &&
            (parentData as any)?.parameters?.input
          ) {
            newReplica.data.structureFilename = (parentData as any).structureFilename;
            newReplica.data.structureEdgeId = edgeId;
          }
        });

        externalOutgoingTargets.forEach((targetId) => {
          const edgeId = `e-${newId}-${targetId}`;
          nextEdges.push({
            id: edgeId,
            source: newId,
            target: targetId,
            type: 'removable',
            animated: true,
            style: { stroke: '#64748b', strokeWidth: 2 },
          });
        });

        keptReplicas.push(newReplica);
      }
    }

    // Ensure all kept replicas and parent have connections to external incoming and outgoing targets
    const existingEdgeKeys = new Set(nextEdges.map((e) => `${e.source}->${e.target}`));

    keptReplicas.forEach((rep) => {
      externalIncomingSources.forEach((sourceId) => {
        const key = `${sourceId}->${rep.id}`;
        if (!existingEdgeKeys.has(key)) {
          existingEdgeKeys.add(key);
          nextEdges.push({
            id: `e-${sourceId}-${rep.id}`,
            source: sourceId,
            target: rep.id,
            type: 'removable',
            animated: true,
            style: { stroke: '#64748b', strokeWidth: 2 },
          });
        }
      });

      externalOutgoingTargets.forEach((targetId) => {
        const key = `${rep.id}->${targetId}`;
        if (!existingEdgeKeys.has(key)) {
          existingEdgeKeys.add(key);
          nextEdges.push({
            id: `e-${rep.id}-${targetId}`,
            source: rep.id,
            target: targetId,
            type: 'removable',
            animated: true,
            style: { stroke: '#64748b', strokeWidth: 2 },
          });
        }
      });
    });

    externalIncomingSources.forEach((sourceId) => {
      const key = `${sourceId}->${parentNode.id}`;
      if (!existingEdgeKeys.has(key)) {
        existingEdgeKeys.add(key);
        nextEdges.push({
          id: `e-${sourceId}-${parentNode.id}`,
          source: sourceId,
          target: parentNode.id,
          type: 'removable',
          animated: true,
          style: { stroke: '#64748b', strokeWidth: 2 },
        });
      }
    });

    externalOutgoingTargets.forEach((targetId) => {
      const key = `${parentNode.id}->${targetId}`;
      if (!existingEdgeKeys.has(key)) {
        existingEdgeKeys.add(key);
        nextEdges.push({
          id: `e-${parentNode.id}-${targetId}`,
          source: parentNode.id,
          target: targetId,
          type: 'removable',
          animated: true,
          style: { stroke: '#64748b', strokeWidth: 2 },
        });
      }
    });

    // Split replicas equally between UP and DOWN sides
    const M_up = Math.ceil(neededReplicas / 2);
    const M_down = Math.floor(neededReplicas / 2);

    const upReplicas = keptReplicas.slice(0, M_up);
    const downReplicas = keptReplicas.slice(M_up);

    // 1. Process UP side:
    // If M_up <= 3: all visible, no expander
    // If M_up > 3: outermost visible, closest visible, intermediate hidden behind three dots
    const upIntermediateIds: string[] = [];
    let upExpanderNode: Node | null = null;
    let upPositioned: Node[] = [];

    if (M_up <= 3) {
      upPositioned = upReplicas.map((rep, idx) => {
        const offset = idx + 1;
        return {
          ...rep,
          hidden: false,
          position: { x: x0 + 82, y: y0 - offset * 46 },
          data: {
            ...rep.data,
            index: idx + 2,
            branchGroupId: groupId,
          },
        };
      });
      // Ensure edges on up side are visible
      const upIds = new Set(upPositioned.map((n) => n.id));
      nextEdges = nextEdges.map((e) =>
        upIds.has(e.target) || upIds.has(e.source) ? { ...e, hidden: false } : e
      );
    } else {
      const closestNode = upReplicas[0];
      const outermostNode = upReplicas[M_up - 1];
      const intermediateNodes = upReplicas.slice(1, M_up - 1);
      intermediateNodes.forEach((n) => upIntermediateIds.push(n.id));

      const upIntermediateSet = new Set(upIntermediateIds);
      nextEdges = nextEdges.map((e) =>
        upIntermediateSet.has(e.target) || upIntermediateSet.has(e.source) ? { ...e, hidden: true } : e
      );
      const upEdgeVisibleSet = new Set([closestNode.id, outermostNode.id]);
      nextEdges = nextEdges.map((e) =>
        upEdgeVisibleSet.has(e.target) || upEdgeVisibleSet.has(e.source) ? { ...e, hidden: false } : e
      );

      const positionedClosest: Node = {
        ...closestNode,
        hidden: false,
        position: { x: x0 + 82, y: y0 - 46 },
        data: { ...closestNode.data, index: 2, branchGroupId: groupId },
      };

      const positionedOutermost: Node = {
        ...outermostNode,
        hidden: false,
        position: { x: x0 + 82, y: y0 - 138 },
        data: { ...outermostNode.data, index: M_up + 1, branchGroupId: groupId },
      };

      const positionedIntermediate: Node[] = intermediateNodes.map((n, i) => ({
        ...n,
        hidden: true,
        position: { x: x0 + 82, y: y0 - 92 },
        data: { ...n.data, index: i + 3, branchGroupId: groupId },
      }));

      upExpanderNode = {
        id: `expander-up-${groupId}`,
        type: 'branchDots',
        position: { x: x0 + 82, y: y0 - 92 },
        data: {
          groupId,
          branchGroupId: groupId,
          side: 'up',
          hiddenCount: intermediateNodes.length,
          totalIntermediate: intermediateNodes.length,
          batchSize: 5,
          isFullyExpanded: false,
          intermediateNodeIds: upIntermediateIds,
          boundaryNodeId: outermostNode.id,
          closestNodeId: closestNode.id,
          onExpandSide: (g: string, s: 'up' | 'down') => expandSideRef.current(g, s),
          onCollapseSide: (g: string, s: 'up' | 'down') => collapseSideRef.current(g, s),
        },
      };

      upPositioned = [positionedClosest, ...positionedIntermediate, positionedOutermost];
    }

    // 2. Process DOWN side:
    // If M_down <= 3: all visible, no expander
    // If M_down > 3: closest visible, outermost visible, intermediate hidden behind three dots
    const downIntermediateIds: string[] = [];
    let downExpanderNode: Node | null = null;
    let downPositioned: Node[] = [];

    if (M_down <= 3) {
      downPositioned = downReplicas.map((rep, idx) => {
        const offset = idx + 1;
        return {
          ...rep,
          hidden: false,
          position: { x: x0 + 82, y: y0 + 82 + (offset - 1) * 46 },
          data: {
            ...rep.data,
            index: M_up + 2 + idx,
            branchGroupId: groupId,
          },
        };
      });
      const downIds = new Set(downPositioned.map((n) => n.id));
      nextEdges = nextEdges.map((e) =>
        downIds.has(e.target) || downIds.has(e.source) ? { ...e, hidden: false } : e
      );
    } else {
      const closestNode = downReplicas[0];
      const outermostNode = downReplicas[M_down - 1];
      const intermediateNodes = downReplicas.slice(1, M_down - 1);
      intermediateNodes.forEach((n) => downIntermediateIds.push(n.id));

      const downIntermediateSet = new Set(downIntermediateIds);
      nextEdges = nextEdges.map((e) =>
        downIntermediateSet.has(e.target) || downIntermediateSet.has(e.source) ? { ...e, hidden: true } : e
      );
      const downEdgeVisibleSet = new Set([closestNode.id, outermostNode.id]);
      nextEdges = nextEdges.map((e) =>
        downEdgeVisibleSet.has(e.target) || downEdgeVisibleSet.has(e.source) ? { ...e, hidden: false } : e
      );

      const positionedClosest: Node = {
        ...closestNode,
        hidden: false,
        position: { x: x0 + 82, y: y0 + 82 },
        data: { ...closestNode.data, index: M_up + 2, branchGroupId: groupId },
      };

      const positionedOutermost: Node = {
        ...outermostNode,
        hidden: false,
        position: { x: x0 + 82, y: y0 + 174 },
        data: { ...outermostNode.data, index: M_up + 1 + M_down, branchGroupId: groupId },
      };

      const positionedIntermediate: Node[] = intermediateNodes.map((n, i) => ({
        ...n,
        hidden: true,
        position: { x: x0 + 82, y: y0 + 128 },
        data: { ...n.data, index: M_up + 3 + i, branchGroupId: groupId },
      }));

      downExpanderNode = {
        id: `expander-down-${groupId}`,
        type: 'branchDots',
        position: { x: x0 + 82, y: y0 + 128 },
        data: {
          groupId,
          branchGroupId: groupId,
          side: 'down',
          hiddenCount: intermediateNodes.length,
          totalIntermediate: intermediateNodes.length,
          batchSize: 5,
          isFullyExpanded: false,
          intermediateNodeIds: downIntermediateIds,
          boundaryNodeId: outermostNode.id,
          closestNodeId: closestNode.id,
          onExpandSide: (g: string, s: 'up' | 'down') => expandSideRef.current(g, s),
          onCollapseSide: (g: string, s: 'up' | 'down') => collapseSideRef.current(g, s),
        },
      };

      downPositioned = [positionedClosest, ...positionedIntermediate, positionedOutermost];
    }

    // Parent node stays at center (x0, y0)
    const updatedParentNode: Node = {
      ...parentNode,
      position: { x: x0, y: y0 },
      data: {
        ...parentNode.data,
        cleanLabel: cleanBase,
        branchGroupId: groupId,
        branchCount: targetCount,
        isParentBranch: true,
        index: 1,
      },
    };

    // Filter out old group nodes (replicas AND expanders) from currentNodes
    const oldGroupIds = new Set(
      currentNodes
        .filter((n) => isGroupMemberNode(n, groupId, parentNode.id))
        .map((n) => n.id)
    );

    const otherNodes = currentNodes.filter(
      (n) => n.id !== parentNode.id && !oldGroupIds.has(n.id)
    );

    const nextNodes = [
      ...otherNodes,
      updatedParentNode,
      ...upPositioned,
      ...(upExpanderNode ? [upExpanderNode] : []),
      ...downPositioned,
      ...(downExpanderNode ? [downExpanderNode] : []),
    ];

    setNodes(nextNodes);
    setEdges(nextEdges);

    if (onGraphChange) {
      onGraphChange({ nodes: nextNodes, edges: nextEdges });
    }
  }, [expandSide, collapseSide, onGraphChange]);

  const deleteNode = useCallback((nodeId: string) => {
    setNodes((nds) => {
      const target = nds.find((n) => n.id === nodeId || (n.data as any)?.originalData?.ui_id === nodeId);
      if (!target) return nds.filter((n) => n.id !== nodeId);

      const targetData = (target.data || {}) as any;
      const groupId = targetData.branchGroupId;

      // If deleting a branchDots expander: unhide all intermediate nodes on that side
      if (target.type === 'branchDots') {
        const intermediateIds = (targetData?.intermediateNodeIds as string[]) || [];
        const unhideSet = new Set(intermediateIds);
        setEdges((eds) => eds.map((e) => (unhideSet.has(e.target) ? { ...e, hidden: false } : e)));
        return nds
          .filter((n) => n.id !== nodeId)
          .map((n) => (unhideSet.has(n.id) ? { ...n, hidden: false } : n));
      }

      // If deleting the parent calculation card: delete all its replicas and expanders too
      if (groupId && (target.id === groupId || targetData.isParentBranch)) {
        return nds.filter((n) => n.id !== nodeId && !isGroupMemberNode(n, groupId, target.id));
      }

      // If deleting an individual circular branch node: re-calculate parallel count
      if (groupId && target.type === 'branchCircle') {
        const parent = nds.find((n) => n.id === groupId || (n.data as any)?.isParentBranch);
        const replicas = nds.filter(
          (n) => (n.data as any)?.branchGroupId === groupId && n.id !== parent?.id && n.id !== nodeId && n.type === 'branchCircle'
        );
        const newTotalCount = replicas.length + 1;
        if (parent) {
          setTimeout(() => setParallelCount(parent.id, newTotalCount), 0);
        }
        return nds.filter((n) => n.id !== nodeId);
      }

      return nds.filter((n) => n.id !== nodeId && (n.data as any)?.originalData?.ui_id !== nodeId);
    });
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
  }, [setParallelCount]);

  useEffect(() => {
    if (onRegisterDeleteHandler) {
      onRegisterDeleteHandler(deleteNode);
    }
  }, [deleteNode, onRegisterDeleteHandler]);

  const replicateNode = useCallback((nodeId: string, count: number) => {
    setParallelCount(nodeId, count);
  }, [setParallelCount]);

  useEffect(() => {
    if (onRegisterReplicateHandler) {
      onRegisterReplicateHandler(replicateNode);
    }
  }, [replicateNode, onRegisterReplicateHandler]);

  // Hydrate from blueprint
  useEffect(() => {
    if (blueprint && blueprint.nodes) {
      const initialNodes: Node[] = blueprint.nodes.map((n, i) => {
        if (n.type === 'structure' || n.node_type === 'structure') {
          return {
            id: n.ui_id || n.id,
            type: 'structure',
            position: n.position || { x: 100, y: 150 },
            sourcePosition: Position.Right,
            data: {
              ...n,
              ...(n.data || {}),
              onFileUpload: (nId: string, f: File) => processStructureFile(f, nId),
            }
          };
        }
        if (n.type === 'branchCircle') {
          return {
            id: n.ui_id || n.id,
            type: 'branchCircle',
            position: n.position || { x: 100, y: 150 },
            sourcePosition: Position.Right,
            targetPosition: Position.Left,
            data: {
              ...n,
              ...(n.data || {}),
              index: (n.data as any)?.index || (n as any).index || 2,
              cleanLabel: n.label || n.script_name,
              branchGroupId: (n.data as any)?.branchGroupId || (n as any).branchGroupId,
            },
          };
        }
        return {
          id: n.ui_id || n.id,
          type: 'default',
          className: 'atomfield-pipeline-node',
          position: n.position || { x: 250 * i + 100, y: 150 },
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          data: { 
            label: n.label || n.script_name, 
            filename: n.filename || n.script_name,
            script_id: n.script_id || n.ui_id || n.id,
            status: n.status || 'Draft', 
            parameters: n.parameters || {},
            default_parameters: n.default_parameters || n.parameters || {},
            originalData: n 
          },
          style: {
            background: statusColors[n.status || 'Draft'] || '#fff',
            color: '#334155',
            fontWeight: 'bold',
            border: '2px solid #94a3b8',
            borderRadius: '12px',
            padding: 0,
            width: 200,
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
          }
        };
      });
      setNodes(initialNodes);
      if (initialNodes.length > 0) {
        setTimeout(() => {
          rfFitView({ maxZoom: 1.23, padding: 0.18 });
        }, 50);
      }
    }
    
    if (blueprint && blueprint.edges) {
      const initialEdges: Edge[] = blueprint.edges.map((e) => ({
        id: `e-${e.upstream_ui_id}-${e.downstream_ui_id}`,
        source: e.upstream_ui_id,
        target: e.downstream_ui_id,
        sourceHandle:
          (e as any).sourceHandle ||
          (e as any).source_handle ||
          (e.upstream_ui_id.includes('structure') ? 'structure-out' : 'source-right'),
        targetHandle: (e as any).targetHandle || (e as any).target_handle || 'target-left',
        type: 'removable',
        animated: true,
        style: { stroke: '#94a3b8', strokeWidth: 2 }
      }));
      setEdges(initialEdges);
    }
  }, [blueprint, rfFitView]);

  // Dynamic End-of-Job Results Viewer Node (Nanoreactor Discovery)
  useEffect(() => {
    if (showResultsNode) {
      setNodes((currentNodes) => {
        if (currentNodes.some((n) => n.id === 'result_viewer_node')) {
          return currentNodes;
        }

        const terminalNode =
          currentNodes.find((n) => n.id === 'xtb_nanoreactor') ||
          currentNodes.find((n) => n.id === 'ts_search_1') ||
          currentNodes.find(
            (n) => n.type !== 'structure' && !edgesRef.current.some((e) => e.source === n.id)
          );

        if (!terminalNode) return currentNodes;

        const resultNode: Node = {
          id: 'result_viewer_node',
          type: 'resultViewer',
          position: {
            x: (terminalNode.position?.x || 380) + 280,
            y: terminalNode.position?.y || 220,
          },
          data: {
            label: 'Reaction Network Explorer',
            subtitle: '3D force graph & text artifacts',
            speciesCount: 7,
            pathwayCount: 6,
            onOpenResults,
          },
        };

        return [...currentNodes, resultNode];
      });

      setEdges((currentEdges) => {
        if (currentEdges.some((e) => e.target === 'result_viewer_node')) {
          return currentEdges;
        }

        const terminalNode =
          nodesRef.current.find((n) => n.id === 'xtb_nanoreactor') ||
          nodesRef.current.find((n) => n.id === 'ts_search_1') ||
          nodesRef.current.find(
            (n) => n.type !== 'structure' && !currentEdges.some((e) => e.source === n.id)
          );

        if (!terminalNode) return currentEdges;

        const resultEdge: Edge = {
          id: `e-${terminalNode.id}-result_viewer_node`,
          source: terminalNode.id,
          target: 'result_viewer_node',
          sourceHandle: 'source-right',
          targetHandle: 'target-left',
          animated: true,
          style: { stroke: '#ea580c', strokeWidth: 2, strokeDasharray: '4 4' },
        };

        return [...currentEdges, resultEdge];
      });
    } else {
      setNodes((currentNodes) =>
        currentNodes.filter((n) => n.id !== 'result_viewer_node')
      );
      setEdges((currentEdges) =>
        currentEdges.filter((e) => e.target !== 'result_viewer_node')
      );
    }
  }, [showResultsNode, onOpenResults]);

  const onNodesChange = useCallback(
    (changes: any[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );

  const onEdgesChange = useCallback(
    (changes: any[]) => {
      const removedEdgeIds = changes.filter((c) => c.type === 'remove').map((c) => c.id);
      let updatedChanges = changes;

      if (removedEdgeIds.length > 0) {
        const removedEdges = edgesRef.current.filter((e) => removedEdgeIds.includes(e.id));
        const sisterEdgeIdsToRemove = new Set<string>();

        removedEdges.forEach((re) => {
          const sNode = nodesRef.current.find((n) => n.id === re.source);
          const tNode = nodesRef.current.find((n) => n.id === re.target);
          const sGroupId = (sNode?.data as any)?.branchGroupId || ((sNode?.data as any)?.isParentBranch ? sNode?.id : null);
          const tGroupId = (tNode?.data as any)?.branchGroupId || ((tNode?.data as any)?.isParentBranch ? tNode?.id : null);

          if (sGroupId || tGroupId) {
            edgesRef.current.forEach((e) => {
              const matchesSource = sGroupId
                ? (e.source === sGroupId || isGroupMemberNode(nodesRef.current.find((n) => n.id === e.source), sGroupId, sGroupId))
                : e.source === re.source;

              const matchesTarget = tGroupId
                ? (e.target === tGroupId || isGroupMemberNode(nodesRef.current.find((n) => n.id === e.target), tGroupId, tGroupId))
                : e.target === re.target;

              if (matchesSource && matchesTarget) {
                sisterEdgeIdsToRemove.add(e.id);
              }
            });
          }
        });

        if (sisterEdgeIdsToRemove.size > 0) {
          const extraRemoves = Array.from(sisterEdgeIdsToRemove)
            .filter((id) => !removedEdgeIds.includes(id))
            .map((id) => ({ type: 'remove', id }));
          updatedChanges = [...changes, ...extraRemoves];
        }

        const allRemovedIds = new Set([...removedEdgeIds, ...Array.from(sisterEdgeIdsToRemove)]);

        setNodes((nds) => {
          let updated = false;
          const newNodes = nds.map((n) => {
            const d = n.data as any;
            if (d?.structureEdgeId && allRemovedIds.has(d.structureEdgeId)) {
              updated = true;
              const newParams = { ...(d.parameters || {}) };
              delete newParams.input;
              return {
                ...n,
                data: {
                  ...d,
                  parameters: newParams,
                  structureEdgeId: undefined,
                  structureFilename: undefined,
                },
              };
            }
            return n;
          });
          return updated ? newNodes : nds;
        });
      }
      setEdges((eds) => applyEdgeChanges(updatedChanges, eds));
    },
    []
  );

  const onConnect = useCallback(
    (params: any) => {
      const currentNodes = nodesRef.current;
      const currentEdges = edgesRef.current;

      const sourceNode = currentNodes.find((n) => n.id === params.source);
      const targetNode = currentNodes.find((n) => n.id === params.target);
      if (!sourceNode || !targetNode) return;

      const sourceData = (sourceNode.data || {}) as any;
      const targetData = (targetNode.data || {}) as any;

      const sourceGroupId = sourceData.branchGroupId || (sourceData.isParentBranch ? sourceNode.id : null);
      const targetGroupId = targetData.branchGroupId || (targetData.isParentBranch ? targetNode.id : null);

      const sourceNodesToConnect: Node[] = sourceGroupId
        ? currentNodes.filter(
            (n) =>
              (n.id === sourceGroupId || isGroupMemberNode(n, sourceGroupId, sourceGroupId)) &&
              n.type !== 'branchDots' &&
              n.type !== 'branchExpander'
          )
        : [sourceNode];

      const targetNodesToConnect: Node[] = targetGroupId
        ? currentNodes.filter(
            (n) =>
              (n.id === targetGroupId || isGroupMemberNode(n, targetGroupId, targetGroupId)) &&
              n.type !== 'branchDots' &&
              n.type !== 'branchExpander'
          )
        : [targetNode];

      const isStructureSource = sourceNode.type === 'structure' || sourceData.workspace_path;
      const workspacePath = isStructureSource
        ? sourceData.workspace_path || (sourceData.filename ? `/workspace/${sourceData.filename}` : '')
        : '';

      if (workspacePath) {
        const targetIdsToUpdate = new Set(targetNodesToConnect.map((n) => n.id));
        setNodes((nds) =>
          nds.map((n) => {
            if (targetIdsToUpdate.has(n.id)) {
              const nData = n.data as any;
              return {
                ...n,
                data: {
                  ...nData,
                  parameters: {
                    ...(nData.parameters || {}),
                    input: workspacePath,
                  },
                  structureFilename: sourceData.filename,
                },
              };
            }
            return n;
          })
        );
      }

      const existingEdgeKeys = new Set(currentEdges.map((e) => `${e.source}->${e.target}`));
      const newEdgesToAdd: Edge[] = [];

      sourceNodesToConnect.forEach((sNode) => {
        targetNodesToConnect.forEach((tNode) => {
          const key = `${sNode.id}->${tNode.id}`;
          if (!existingEdgeKeys.has(key)) {
            existingEdgeKeys.add(key);
            const edgeId = `e-${sNode.id}-${tNode.id}`;
            const isHidden = sNode.hidden === true || tNode.hidden === true;
            newEdgesToAdd.push({
              id: edgeId,
              source: sNode.id,
              target: tNode.id,
              sourceHandle: params.sourceHandle,
              targetHandle: params.targetHandle,
              type: 'removable',
              animated: true,
              hidden: isHidden,
              style: { stroke: '#64748b', strokeWidth: 2 },
            });
          }
        });
      });

      if (newEdgesToAdd.length > 0) {
        setEdges((eds) => [...eds, ...newEdgesToAdd]);
      }
    },
    []
  );

  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: any) =>
      setEdges((els) => reconnectEdge(oldEdge, newConnection, els)),
    []
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      if (!isEditable) return;

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      // 1. Direct desktop file drop
      if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
        const file = event.dataTransfer.files[0];
        processStructureFile(file, undefined, position);
        return;
      }

      // 2. Dragged from sidebar
      const rawData = event.dataTransfer.getData('application/reactflow');
      const fallbackName = event.dataTransfer.getData('scriptName');

      if (!rawData && !fallbackName) {
        return;
      }

      let scriptData: any = null;
      try {
        scriptData = JSON.parse(rawData);
      } catch {
        scriptData = {
          id: fallbackName || rawData,
          title: fallbackName || rawData,
          default_parameters: {}
        };
      }

      if (scriptData.type === 'structure') {
        const newNodeId = uuidv4();
        const newNode: Node = {
          id: newNodeId,
          type: 'structure',
          position,
          sourcePosition: Position.Right,
          data: {
            onFileUpload: (nId: string, f: File) => processStructureFile(f, nId),
          }
        };
        setNodes((nds) => nds.concat(newNode));
        return;
      }

      const newNode: Node = {
        id: uuidv4(),
        type: 'default',
        className: 'atomfield-pipeline-node',
        position,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: { 
          label: scriptData.title || scriptData.name || fallbackName || 'Untitled Script',
          script_id: scriptData.id,
          filename: scriptData.filename,
          status: 'Draft',
          parameters: scriptData.default_parameters || {},
          default_parameters: scriptData.default_parameters || {}
        },
        style: {
          background: statusColors['Draft'],
          color: '#334155',
          fontWeight: 'bold',
          border: '2px solid #94a3b8',
          borderRadius: '12px',
          padding: 0,
          width: 200,
          boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
        }
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, isEditable, processStructureFile]
  );

  const onNodeClickInternal = (_: React.MouseEvent, node: Node) => {
    if (node.type === 'branchExpander' || node.type === 'branchDots' || node.type === 'structure') {
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      setClickedNodeId(null);
      if (onNodeClick) {
        onNodeClick(node);
      }
      return;
    }

    if (onNodeClick) {
      onNodeClick(node);
    }

    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
    }
    clickTimerRef.current = setTimeout(() => {
      setClickedNodeId(node.id);
      clickTimerRef.current = null;
    }, 250);
  };

  const onNodeDoubleClickInternal = (_: React.MouseEvent, node: Node) => {
    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
    setClickedNodeId(null);

    if (node.type === 'branchExpander' || node.type === 'branchDots') return;
    if (node.type === 'resultViewer' || node.id === 'result_viewer_node') {
      if (onOpenResults) {
        onOpenResults();
      }
      return;
    }
    if (!onNodeDoubleClick) return;

    const nodeData = node.data as any;
    if (node.type === 'structure') {
      onNodeDoubleClick({
        id: node.id,
        type: 'structure',
        title: nodeData.filename || 'Structure Input',
        ...nodeData,
        data: nodeData
      });
      return;
    }

    if (nodeData?.originalData) {
      onNodeDoubleClick({
        ...nodeData.originalData,
        id: node.id,
        type: node.type || 'default',
        status: nodeData.status || nodeData.originalData.status,
        logs: nodeData.logs,
        artifacts: nodeData.artifacts,
        job_id: nodeData.job_id,
        parameters: nodeData.parameters !== undefined ? nodeData.parameters : nodeData.originalData.parameters,
        default_parameters: nodeData.default_parameters || nodeData.originalData.default_parameters,
        data: nodeData
      });
    } else {
      onNodeDoubleClick({
        ...node,
        type: node.type || 'default',
        status: nodeData?.status || (node as any).status || 'Draft',
        logs: nodeData?.logs,
        artifacts: nodeData?.artifacts,
        job_id: nodeData?.job_id,
        parameters: nodeData?.parameters,
        default_parameters: nodeData?.default_parameters,
        data: nodeData
      });
    }
  };

  const onPaneClick = () => {
    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
    setClickedNodeId(null);
  };

  const handleNodesDelete = useCallback(
    (deleted: Node[]) => {
      const deletedExpanders = deleted.filter(
        (n) => n.type === 'branchExpander' || n.type === 'branchDots'
      );
      if (deletedExpanders.length > 0) {
        const allUnhideIds = new Set<string>();
        deletedExpanders.forEach((exp) => {
          const intermediateIds = (exp.data?.intermediateNodeIds as string[]) || [];
          intermediateIds.forEach((id) => allUnhideIds.add(id));
        });

        if (allUnhideIds.size > 0) {
          setNodes((nds) =>
            nds.map((n) => {
              if (allUnhideIds.has(n.id)) {
                return { ...n, hidden: false };
              }
              return n;
            })
          );
          setEdges((eds) =>
            eds.map((e) => {
              if (allUnhideIds.has(e.target)) {
                return { ...e, hidden: false };
              }
              return e;
            })
          );
        }
      }

      if (onNodesDelete) onNodesDelete(deleted);
    },
    [onNodesDelete]
  );

  const activeToolbarNode = nodes.find((n) => n.id === activeToolbarNodeId);
  const canShowToolbar =
    activeToolbarNodeId &&
    activeToolbarNode &&
    activeToolbarNode.type !== 'branchExpander' &&
    activeToolbarNode.type !== 'branchDots' &&
    activeToolbarNode.type !== 'structure';

  const activeGroupCount =
    (activeToolbarNode?.data as any)?.branchCount ||
    ((activeToolbarNode?.data as any)?.branchGroupId
      ? nodes.filter(
          (n) =>
            n.type === 'branchCircle' &&
            (n.data as any)?.branchGroupId &&
            (n.data as any)?.branchGroupId === (activeToolbarNode?.data as any)?.branchGroupId
        ).length + 1
      : 1);

  return (
    <div className="w-full h-full" ref={reactFlowWrapper}>
      <ReactFlow 
        nodes={nodes} 
        edges={edges} 
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={{ type: 'removable' }}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onReconnect={onReconnect}
        onNodeClick={onNodeClickInternal}
        onNodeDoubleClick={onNodeDoubleClickInternal}
        onPaneClick={onPaneClick}
        onNodesDelete={handleNodesDelete}
        deleteKeyCode={['Backspace', 'Delete']}
        onDrop={onDrop}
        onDragOver={onDragOver}
        fitView
        fitViewOptions={{ maxZoom: 1.23, padding: 0.18 }}
        minZoom={0.15}
        maxZoom={2.0}
        defaultViewport={{ x: 50, y: 50, zoom: 1.23 }}
      >
        <Background color="#ccc" gap={16} />
        <Controls showInteractive={false} />

        {canShowToolbar && (
          <NodeToolbar
            nodeId={activeToolbarNodeId}
            position={Position.Right}
            offset={16}
            isVisible={true}
          >
            <div data-toolbar="true" className="flex items-center gap-1.5 bg-white border border-slate-300 rounded-lg shadow-lg px-2.5 py-1 text-xs select-none">
              <span className="font-bold text-slate-700 flex items-center gap-1 text-[11px] pr-1.5 border-r border-slate-200">
                <GitBranch className="w-3.5 h-3.5 text-orange-500" />
                Parallel:
              </span>
              {[2, 3, 5, 10].map((cnt) => (
                <button
                  key={cnt}
                  onClick={(e) => {
                    e.stopPropagation();
                    setParallelCount(activeToolbarNodeId, cnt);
                  }}
                  className={`px-1.5 py-0.5 font-bold rounded text-xs transition-colors cursor-pointer ${
                    activeGroupCount === cnt
                      ? 'bg-orange-500 text-white shadow-2xs'
                      : 'text-slate-700 hover:text-orange-600 hover:bg-orange-50'
                  }`}
                  title={`Set to ${cnt} parallel jobs`}
                >
                  &times;{cnt}
                </button>
              ))}
              <div className="flex items-center gap-1 pl-1 border-l border-slate-200">
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={customToolbarCount}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) =>
                    setCustomToolbarCount(
                      Math.max(1, parseInt(e.target.value) || 1)
                    )
                  }
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.stopPropagation();
                      setParallelCount(activeToolbarNodeId, customToolbarCount);
                    }
                  }}
                  className="w-12 px-1 py-0.5 text-xs font-bold text-center bg-slate-50 border border-slate-300 rounded text-slate-800 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  placeholder="Count"
                />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setParallelCount(activeToolbarNodeId, customToolbarCount);
                  }}
                  className="px-2 py-0.5 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 rounded shadow-2xs transition-colors cursor-pointer"
                  title="Set parallel jobs count"
                >
                  Set
                </button>
                {activeGroupCount > 1 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setParallelCount(activeToolbarNodeId, 1);
                    }}
                    className="px-1.5 py-0.5 text-[10px] font-bold text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors cursor-pointer ml-0.5"
                    title="Reset to single job (remove parallelization)"
                  >
                    Reset
                  </button>
                )}
              </div>
            </div>
          </NodeToolbar>
        )}
      </ReactFlow>
    </div>
  );
}
