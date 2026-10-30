import React, { useRef } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FileText } from 'lucide-react';
import { HANDLE_CLASS, nodeBox } from './nodeStyle';

export interface StructureNodeData {
  filename?: string;
  format?: string;
  raw_content?: string;
  size_bytes?: number;
  atom_count?: number;
  formula?: string;
  workspace_path?: string;
  comment?: string;
  elements?: Record<string, number>;
  onFileUpload?: (nodeId: string, file: File) => void;
}

// Every side takes links in and out, like a step's.
const HANDLES = [
  { id: 'structure-out', type: 'source', position: Position.Right },
  { id: 'structure-in-right', type: 'target', position: Position.Right },
  { id: 'structure-out-top', type: 'source', position: Position.Top },
  { id: 'structure-in-top', type: 'target', position: Position.Top },
  { id: 'structure-out-bottom', type: 'source', position: Position.Bottom },
  { id: 'structure-in-bottom', type: 'target', position: Position.Bottom },
  { id: 'structure-out-left', type: 'source', position: Position.Left },
  { id: 'structure-in-left', type: 'target', position: Position.Left },
] as const;

/**
 * An input file: its name, or "Drop a file" (dashed) until one is
 * dropped or chosen.
 */
export default function StructureNode({ id, data, selected }: any) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nodeData = (data || {}) as StructureNodeData;
  const isPopulated = !!nodeData.filename;
  const filename = nodeData.filename || 'Structure Input';

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      if (nodeData.onFileUpload) {
        nodeData.onFileUpload(id, file);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (nodeData.onFileUpload) {
        nodeData.onFileUpload(id, file);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
  };

  // Subtitle text: Formula if detected, or Format/Atom info, or empty prompt
  const subtitle = nodeData.formula && nodeData.formula !== 'Unknown'
    ? `${nodeData.formula}${nodeData.atom_count ? ` (${nodeData.atom_count})` : ''}`
    : isPopulated
    ? `${nodeData.format || 'XYZ'}${nodeData.atom_count ? ` • ${nodeData.atom_count} atoms` : ''}`
    : 'Drop structure';

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      className={`${nodeBox(selected, !isPopulated)} cursor-pointer`}
      title={isPopulated ? `${filename} · ${subtitle}` : 'Drop a file here'}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".xyz,.cif,.sdf,.mol,.pdb,.in"
        className="hidden"
        onChange={handleFileChange}
      />
      {HANDLES.map((handle) => (
        <Handle
          key={handle.id}
          id={handle.id}
          type={handle.type}
          position={handle.position}
          className={HANDLE_CLASS}
        />
      ))}
      <FileText size={16} className="shrink-0 text-stone-500" />
      <span
        className={`truncate text-sm font-medium ${
          isPopulated ? 'text-stone-900' : 'text-stone-500'
        }`}
      >
        {isPopulated ? filename : 'Drop a file'}
      </span>
    </div>
  );
}
