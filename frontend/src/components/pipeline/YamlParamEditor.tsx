import { useMemo } from 'react';

interface YamlParamEditorProps {
  parameters: Record<string, any>;
  onChange: (newParams: Record<string, any>) => void;
}

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
                ) : (
                  <input
                    type={valType === 'number' ? 'number' : 'text'}
                    step={valType === 'number' ? 'any' : undefined}
                    value={val !== undefined && val !== null ? val : ''}
                    onChange={(e) => handleValueChange(key, e.target.value, valType)}
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
