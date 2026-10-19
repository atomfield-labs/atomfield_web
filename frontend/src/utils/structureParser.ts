/**
 * frontend/src/utils/structureParser.ts
 * Fast in-browser parser for chemical structure files (.xyz, .cif, .sdf, .mol, .pdb).
 */

export interface ParsedStructure {
  filename: string;
  format: string;
  size_bytes: number;
  line_count: number;
  atom_count: number;
  formula?: string;
  comment?: string;
  elements?: Record<string, number>;
  bounding_box?: {
    span_x: number;
    span_y: number;
    span_z: number;
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    min_z: number;
    max_z: number;
  };
}

/**
 * Format chemical formula using standard Hill notation (C first, then H, then alphabetical).
 */
export function formatHillFormula(counts: Record<string, number>): string {
  const parts: string[] = [];
  if ('C' in counts) {
    const cCount = counts['C'];
    parts.push(`C${cCount > 1 ? cCount : ''}`);
    if ('H' in counts) {
      const hCount = counts['H'];
      parts.push(`H${hCount > 1 ? hCount : ''}`);
    }
    const otherKeys = Object.keys(counts).filter(k => k !== 'C' && k !== 'H').sort();
    for (const k of otherKeys) {
      const cnt = counts[k];
      parts.push(`${k}${cnt > 1 ? cnt : ''}`);
    }
  } else {
    const sortedKeys = Object.keys(counts).sort();
    for (const k of sortedKeys) {
      const cnt = counts[k];
      parts.push(`${k}${cnt > 1 ? cnt : ''}`);
    }
  }
  return parts.join('') || 'Unknown';
}

/**
 * Parse standard .xyz content string in the browser.
 */
function parseXYZ(filename: string, content: string): ParsedStructure {
  const lines = content.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const rawLines = content.split(/\r?\n/);
  
  let expectedAtomCount = 0;
  let comment = '';
  const elements: Record<string, number> = {};
  const xs: number[] = [];
  const ys: number[] = [];
  const zs: number[] = [];

  if (lines.length > 0) {
    const parsedCount = parseInt(lines[0], 10);
    expectedAtomCount = isNaN(parsedCount) ? lines.length - 1 : parsedCount;
  }
  if (lines.length > 1) {
    comment = lines[1];
  }

  const coordLines = lines.slice(2);
  let parsedAtoms = 0;

  for (const line of coordLines) {
    const parts = line.split(/\s+/);
    if (parts.length >= 4) {
      const el = parts[0].charAt(0).toUpperCase() + parts[0].slice(1).toLowerCase();
      const x = parseFloat(parts[1]);
      const y = parseFloat(parts[2]);
      const z = parseFloat(parts[3]);

      if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
        elements[el] = (elements[el] || 0) + 1;
        xs.push(x);
        ys.push(y);
        zs.push(z);
        parsedAtoms++;
      }
    }
  }

  const finalAtomCount = parsedAtoms > 0 ? parsedAtoms : expectedAtomCount;
  const formula = formatHillFormula(elements);

  let bounding_box: ParsedStructure['bounding_box'] | undefined;
  if (xs.length > 0 && ys.length > 0 && zs.length > 0) {
    const min_x = Math.min(...xs);
    const max_x = Math.max(...xs);
    const min_y = Math.min(...ys);
    const max_y = Math.max(...ys);
    const min_z = Math.min(...zs);
    const max_z = Math.max(...zs);

    bounding_box = {
      min_x: Number(min_x.toFixed(3)),
      max_x: Number(max_x.toFixed(3)),
      span_x: Number((max_x - min_x).toFixed(3)),
      min_y: Number(min_y.toFixed(3)),
      max_y: Number(max_y.toFixed(3)),
      span_y: Number((max_y - min_y).toFixed(3)),
      min_z: Number(min_z.toFixed(3)),
      max_z: Number(max_z.toFixed(3)),
      span_z: Number((max_z - min_z).toFixed(3)),
    };
  }

  return {
    filename,
    format: 'XYZ',
    size_bytes: new Blob([content]).size,
    line_count: rawLines.length,
    atom_count: finalAtomCount,
    formula,
    comment,
    elements,
    bounding_box,
  };
}

/**
 * General parser for other molecular formats (.cif, .sdf, .mol, .pdb).
 */
export function parseStructureFile(filename: string, content: string): ParsedStructure {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const rawLines = content.split(/\r?\n/);
  const size_bytes = new Blob([content]).size;

  if (ext === 'xyz') {
    return parseXYZ(filename, content);
  }

  if (ext === 'pdb') {
    let atomCount = 0;
    const elements: Record<string, number> = {};
    for (const line of rawLines) {
      if (line.startsWith('ATOM') || line.startsWith('HETATM')) {
        atomCount++;
        const el = line.substring(76, 78).trim() || line.substring(12, 14).trim();
        if (el) {
          const capitalized = el.charAt(0).toUpperCase() + el.slice(1).toLowerCase();
          elements[capitalized] = (elements[capitalized] || 0) + 1;
        }
      }
    }
    return {
      filename,
      format: 'PDB',
      size_bytes,
      line_count: rawLines.length,
      atom_count: atomCount,
      formula: Object.keys(elements).length > 0 ? formatHillFormula(elements) : undefined,
      comment: rawLines.find(l => l.startsWith('HEADER') || l.startsWith('TITLE'))?.substring(10).trim() || 'PDB Structure',
      elements,
    };
  }

  if (ext === 'sdf' || ext === 'mol') {
    let atomCount = 0;
    // SDF header usually has atom count on line 4
    if (rawLines.length >= 4) {
      const countsLine = rawLines[3];
      const parsedAtoms = parseInt(countsLine.substring(0, 3).trim(), 10);
      if (!isNaN(parsedAtoms)) {
        atomCount = parsedAtoms;
      }
    }
    return {
      filename,
      format: ext.toUpperCase(),
      size_bytes,
      line_count: rawLines.length,
      atom_count: atomCount,
      comment: rawLines[0]?.trim() || `${ext.toUpperCase()} Structure`,
    };
  }

  if (ext === 'cif') {
    return {
      filename,
      format: 'CIF',
      size_bytes,
      line_count: rawLines.length,
      atom_count: rawLines.filter(l => l.startsWith('_atom_site_')).length || 0,
      comment: rawLines.find(l => l.startsWith('data_'))?.trim() || 'Crystallographic Information File',
    };
  }

  return {
    filename,
    format: ext.toUpperCase() || 'FILE',
    size_bytes,
    line_count: rawLines.length,
    atom_count: 0,
    comment: filename,
  };
}
