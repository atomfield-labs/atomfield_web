import React from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  type EdgeProps,
} from '@xyflow/react';

// Shown on the selected link; red only as you are about to remove it.
const REMOVE_BUTTON = [
  'w-4 h-4 rounded-full bg-white border border-stone-200 text-stone-400',
  'hover:text-white hover:bg-red-600 hover:border-red-600',
  'flex items-center justify-center text-[10px] leading-none',
  'transition-colors cursor-pointer',
].join(' ');

export default function RemovableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  selected = false,
}: EdgeProps) {
  const { deleteElements } = useReactFlow();
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const onEdgeClick = (evt: React.MouseEvent) => {
    evt.stopPropagation();
    deleteElements({ edges: [{ id }] });
  };

  // The remove button shows only on the selected link: one at a time.
  if (!selected) {
    return <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />;
  }
  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          <button
            type="button"
            onClick={onEdgeClick}
            title="Delete connection"
            className={REMOVE_BUTTON}
          >
            &times;
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
