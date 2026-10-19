import React, { useRef } from 'react';
import { Handle, Position } from '@xyflow/react';
import CH4Icon from '../icons/CH4Icon';

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
      className={`relative w-[165px] rounded-lg border-2 transition-all shadow-xs select-none cursor-pointer ${
        selected
          ? 'border-orange-600 bg-orange-50/90 ring-2 ring-orange-400/30 shadow-sm'
          : isPopulated
          ? 'border-slate-400 bg-white hover:bg-orange-50/80 hover:border-orange-400 hover:shadow-sm'
          : 'border-dashed border-slate-300 bg-slate-50 hover:bg-orange-50/80 hover:border-orange-400'
      }`}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".xyz,.cif,.sdf,.mol,.pdb"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* 4-Way Output/Input Connection Joints (Static on Box Lines) */}
      {/* 1. Right Joint */}
      <Handle
        type="source"
        position={Position.Right}
        id="structure-out"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />
      <Handle
        type="target"
        position={Position.Right}
        id="structure-in-right"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />

      {/* 2. Top Joint */}
      <Handle
        type="source"
        position={Position.Top}
        id="structure-out-top"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />
      <Handle
        type="target"
        position={Position.Top}
        id="structure-in-top"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />

      {/* 3. Bottom Joint */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="structure-out-bottom"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id="structure-in-bottom"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />

      {/* 4. Left Joint */}
      <Handle
        type="source"
        position={Position.Left}
        id="structure-out-left"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="structure-in-left"
        className="!w-2 !h-2 !bg-slate-400 !border !border-white shadow-2xs z-10 cursor-crosshair"
      />

      {/* Padded Content inside the box */}
      <div className="px-2.5 py-2 flex items-center justify-between gap-2">
        {/* Left Content: Ball & Stick CH4 Icon + Title & Subtitle */}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <div
            className={`w-7 h-7 shrink-0 rounded-md flex items-center justify-center transition-colors ${
              selected
                ? 'bg-slate-200 text-slate-800'
                : isPopulated
                ? 'bg-slate-100 text-slate-700 border border-slate-200/80 shadow-2xs'
                : 'bg-slate-100/70 text-slate-400 border border-slate-200/50'
            }`}
            title="Molecular Structure"
          >
            <CH4Icon size={18} className="w-4.5 h-4.5" />
          </div>

          <div className="flex flex-col min-w-0 pr-1">
            <span 
              className="font-bold text-xs text-slate-800 truncate leading-tight" 
              title={filename}
            >
              {filename}
            </span>
            <span 
              className="text-[9px] font-mono text-slate-500 font-medium truncate leading-tight mt-0.5"
              title={subtitle}
            >
              {subtitle}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
