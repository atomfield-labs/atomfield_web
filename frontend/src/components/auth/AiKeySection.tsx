import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { describeError } from '../../api/client';
import { aiService } from '../../api/services';
import { useAiKey } from '../../hooks/useAiKey';
import type { AiKeyState, AiVendor, AiVendorView } from '../../types/api';
import { Dropdown, TextBox } from '../widgets';
import { SECTION_TITLE } from './accountStyle';

const NOTE = 'text-[13px] text-stone-500';
const WARNING = [
  'px-3 py-2 rounded-md bg-amber-50 border border-amber-200',
  'text-[13px] text-amber-900',
].join(' ');
const PROBLEM = 'text-[13px] text-red-600';
const LABEL = 'block mb-1 text-xs text-stone-600';
const SAVE = [
  'h-8 px-3 rounded-md bg-orange-600 hover:bg-orange-500 text-white',
  'text-xs font-semibold transition-colors cursor-pointer',
  'disabled:opacity-50 disabled:cursor-default',
].join(' ');
const REMOVE = [
  'text-xs text-stone-500 hover:text-red-600 transition-colors',
  'cursor-pointer',
].join(' ');
const FORM_ROW = 'grid grid-cols-[9rem_1fr_auto] gap-2 items-end';
const NO_SECRET = 'This server has no AI secret set, so AI help is off.';
const COULD_NOT_SAVE = 'Could not save the key. Try again.';
const COULD_NOT_CHANGE = 'Could not change the model. Try again.';
const COULD_NOT_REMOVE = 'Could not remove the key. Try again.';

/**
 * What a click on an AI button does, and any warning about this vendor.
 */
function WhatGetsSent({ vendor }: { vendor: AiVendorView }) {
  return (
    <>
      <p className={NOTE}>
        Clicking an AI button sends that step's small files to {vendor.title},
        under your key.
      </p>
      {vendor.warning && <p className={WARNING}>{vendor.warning}</p>}
    </>
  );
}

/**
 * Adding a key: the vendor checks it before it is saved.
 */
function NewKey({
  vendors,
  onSaved,
}: {
  vendors: AiVendorView[];
  onSaved: (state: AiKeyState) => void;
}) {
  const [vendorId, setVendorId] = useState<AiVendor>(vendors[0].id);
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const vendor = vendors.find((item) => item.id === vendorId) ?? vendors[0];

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!key) return;
    setBusy(true);
    setProblem(null);
    try {
      onSaved(await aiService.saveKey(vendorId, key));
    } catch (error) {
      setProblem(describeError(error, COULD_NOT_SAVE));
      setBusy(false);
    }
  };

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => void save(event)}
    >
      <div className={FORM_ROW}>
        <div>
          <label
            htmlFor="ai-vendor"
            className={LABEL}
          >
            Vendor
          </label>
          <Dropdown
            id="ai-vendor"
            options={vendors.map((item) => ({
              label: item.title,
              value: item.id,
            }))}
            value={vendorId}
            onChange={(value) => setVendorId(value as AiVendor)}
          />
        </div>
        <div>
          <label
            htmlFor="ai-key"
            className={LABEL}
          >
            Key
          </label>
          <TextBox
            id="ai-key"
            secret
            value={key}
            onChange={setKey}
          />
        </div>
        <button
          type="submit"
          disabled={busy || !key}
          className={SAVE}
        >
          {busy ? 'Checking...' : 'Check and save'}
        </button>
      </div>
      {problem && (
        <p
          role="alert"
          className={PROBLEM}
        >
          {problem}
        </p>
      )}
      <WhatGetsSent vendor={vendor} />
    </form>
  );
}

/**
 * The saved key: its vendor and last characters, the model it asks, and
 * a way to remove it. The model menu comes from the vendor.
 */
function SavedKey({
  state,
  onChanged,
}: {
  state: AiKeyState;
  onChanged: (state: AiKeyState) => void;
}) {
  const saved = state.saved!;
  const [models, setModels] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const vendor = state.vendors.find((item) => item.id === saved.vendor)!;
  const choices = [...new Set([saved.model, ...models])];

  useEffect(() => {
    let active = true;
    aiService
      .models()
      .then((found) => active && setModels(found))
      .catch(() => active && setModels([]));
    return () => {
      active = false;
    };
  }, []);

  const choose = async (model: string) => {
    setProblem(null);
    try {
      onChanged(await aiService.chooseModel(model));
    } catch (error) {
      setProblem(describeError(error, COULD_NOT_CHANGE));
    }
  };

  const remove = async () => {
    setProblem(null);
    try {
      await aiService.removeKey();
      onChanged({ ...state, saved: null });
    } catch (error) {
      setProblem(describeError(error, COULD_NOT_REMOVE));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-stone-700">
          {vendor.title}, key ending {saved.key_ending}
        </span>
        <button
          type="button"
          className={REMOVE}
          onClick={() => void remove()}
        >
          Remove
        </button>
      </div>
      <div>
        <label
          htmlFor="ai-model"
          className={LABEL}
        >
          Model
        </label>
        <Dropdown
          id="ai-model"
          options={choices.map((model) => ({ label: model, value: model }))}
          value={saved.model}
          onChange={(value) => void choose(value as string)}
        />
      </div>
      {problem && (
        <p
          role="alert"
          className={PROBLEM}
        >
          {problem}
        </p>
      )}
      <WhatGetsSent vendor={vendor} />
    </div>
  );
}

/**
 * The person's own key for an AI vendor, which AI help on a step uses.
 */
export default function AiKeySection() {
  const { state, setState } = useAiKey();
  if (!state) return null;
  return (
    <section className="space-y-3">
      <h2 className={SECTION_TITLE}>AI key</h2>
      {!state.available && <p className={NOTE}>{NO_SECRET}</p>}
      {state.available && !state.saved && (
        <NewKey
          vendors={state.vendors}
          onSaved={setState}
        />
      )}
      {state.available && state.saved && (
        <SavedKey
          state={state}
          onChanged={setState}
        />
      )}
    </section>
  );
}
