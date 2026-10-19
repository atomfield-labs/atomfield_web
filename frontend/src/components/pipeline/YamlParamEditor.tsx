import { useMemo } from 'react';

interface YamlParamEditorProps {
  parameters: Record<string, any>;
  onChange: (newParams: Record<string, any>) => void;
}

const PARAM_OPTIONS: Record<string, string[]> = {
  solvent: [
    'none',
    'water',
    'acetonitrile',
    'methanol',
    'ethanol',
    'thf',
    'dmso',
    'toluene',
    'chloroform',
    'ch2cl2',
    'hexane',
    'benzene',
    'ether',
  ],
  optlevel: ['crude', 'sloppy', 'loose', 'lax', 'normal', 'tight', 'verytight', 'vtight'],
  rxn_filter: ['smiles', 'formula', 'graph', 'none'],
  engine: ['sevennet', 'mace', 'chgnet', 'm3gnet'],
  model: ['7net-0', '7net-0_22M', 'small', 'medium', 'large', 'mace_mp_0', 'chgnet_0.3.0'],
  ts_search: ['sella_neb', 'sella', 'neb', 'dimer'],
  ts_engine: ['sevennet', 'mace', 'xtb', 'dft'],
  neb_engine: ['sevennet', 'mace', 'xtb'],
  refine: ['sevennet', 'mace', 'xtb', 'none'],
  device: ['cpu', 'cuda', 'mps'],
};

export default function YamlParamEditor({
  parameters,
  onChange,
}: YamlParamEditorProps) {
  // Handle direct value change
  const handleValueChange = (key: string, rawVal: string, originalType: string) => {
    let coercedValue: any = rawVal;
    if (originalType === 'boolean') {
      coercedValue = rawVal === 'true';
    } else if (originalType === 'number') {
      const num = Number(rawVal);
      coercedValue = isNaN(num) ? rawVal : num;
    } else {
      if (rawVal.toLowerCase() === 'true') coercedValue = true;
      else if (rawVal.toLowerCase() === 'false') coercedValue = false;
      else if (!isNaN(Number(rawVal)) && rawVal.trim() !== '') coercedValue = Number(rawVal);
      else coercedValue = rawVal;
    }

    onChange({
      ...(parameters || {}),
      [key]: coercedValue,
    });
  };

  const keys = useMemo(() => Object.keys(parameters || {}), [parameters]);

  return (
    <div className="flex flex-col font-mono text-xs">
      {/* Clean Document Flow: Key and Value adjacent without artificial separation */}
      <div className="space-y-1">
        {keys.length === 0 ? (
          <div className="py-2 text-slate-400 italic text-xs">
            # no parameters configured
          </div>
        ) : (
          keys.map((key) => {
            const val = parameters[key];
            const valType = typeof val;
            const isBool = valType === 'boolean';
            const options = typeof val === 'string' ? PARAM_OPTIONS[key.toLowerCase()] : null;

            return (
              <div
                key={key}
                className="flex items-center py-0.5 group"
              >
                {/* YAML Key (ORANGE) */}
                <span className="text-orange-600 font-bold select-none shrink-0">
                  {key}
                </span>
                <span className="text-slate-400 select-none mr-2">:</span>

                {/* YAML Value (VIOLET) - Left-aligned right beside key */}
                {isBool ? (
                  <button
                    type="button"
                    onClick={() => handleValueChange(key, (!val).toString(), 'boolean')}
                    className="font-bold text-violet-600 hover:text-violet-700 hover:underline select-none transition-colors"
                  >
                    {val ? 'true' : 'false'}
                  </button>
                ) : valType === 'number' ? (
                  <input
                    type="number"
                    step="any"
                    value={val !== undefined && val !== null ? val : ''}
                    onChange={(e) => handleValueChange(key, e.target.value, 'number')}
                    className="flex-1 max-w-[240px] text-left font-semibold text-violet-600 bg-transparent border-0 focus:outline-none focus:border-b focus:border-violet-400 px-0 py-0 text-xs"
                  />
                ) : options ? (
                  <div className="relative inline-flex items-center group/select">
                    <select
                      value={val !== undefined && val !== null ? String(val) : ''}
                      onChange={(e) => handleValueChange(key, e.target.value, 'string')}
                      className="appearance-none bg-transparent font-semibold text-violet-600 hover:text-violet-700 text-xs pr-4 pl-0 py-0 border-0 focus:outline-none focus:border-b focus:border-violet-400 cursor-pointer rounded-none"
                    >
                      {Array.from(new Set([val ? String(val) : '', ...options]))
                        .filter(Boolean)
                        .map((opt) => (
                          <option key={opt} value={opt} className="bg-white text-slate-800 font-mono text-xs">
                            {opt}
                          </option>
                        ))}
                    </select>
                    <span className="pointer-events-none -ml-3 text-[9px] text-violet-400 group-hover/select:text-violet-600 select-none">
                      ▾
                    </span>
                  </div>
                ) : (
                  <input
                    type="text"
                    value={val !== undefined && val !== null ? val : ''}
                    onChange={(e) => handleValueChange(key, e.target.value, 'string')}
                    className="flex-1 max-w-[240px] text-left font-semibold text-violet-600 bg-transparent border-0 focus:outline-none focus:border-b focus:border-violet-400 px-0 py-0 text-xs"
                  />
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
