import PairForm from './PairForm';

/**
 * Where an agent's link leads: connect the computer it runs on.
 */
export default function PairPage({ code }: { code: string }) {
  return (
    <div className="min-h-full bg-white px-6 pt-28 pb-16">
      <div className="mx-auto max-w-md space-y-6">
        <h1 className="text-2xl font-semibold text-stone-900">
          Connect a computer
        </h1>
        <PairForm initialCode={code} />
      </div>
    </div>
  );
}
