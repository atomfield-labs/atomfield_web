import { useEffect, useState } from 'react';
import { authService } from '../../api/services/authService';
import { useSignedInAccount } from '../../hooks/useAccount';
import type { UserStatsResponse } from '../../types/api';
import { SECTION_TITLE } from './accountStyle';
import AiKeySection from './AiKeySection';

function Quota({ stats }: { stats: UserStatsResponse }) {
  const left = Math.max(0, stats.quota_remaining);
  const share = stats.quota_limit ? left / stats.quota_limit : 0;
  const running = stats.running_jobs + stats.pending_jobs;
  return (
    <section className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className={SECTION_TITLE}>Jobs left</span>
        <span className="text-stone-600">
          {left} of {stats.quota_limit}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-stone-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-orange-600"
          style={{ width: `${Math.round(share * 100)}%` }}
        />
      </div>
      <p className="text-[13px] text-stone-500">
        {stats.total_jobs} jobs · {stats.success_jobs} finished ·{' '}
        {stats.failed_jobs} failed · {running} running
      </p>
    </section>
  );
}

/**
 * Who you are, how many jobs you have left, and your key for AI help.
 */
export default function AccountPage() {
  const account = useSignedInAccount();
  const [stats, setStats] = useState<UserStatsResponse | null>(null);

  useEffect(() => {
    let current = true;
    void authService.getStats().then((loaded) => {
      if (current) setStats(loaded);
    });
    return () => {
      current = false;
    };
  }, []);

  return (
    <div className="min-h-full bg-white px-6 pt-28 pb-16">
      <div className="mx-auto max-w-xl space-y-10">
        <header>
          <h1 className="text-2xl font-semibold text-stone-900">
            {account.label || account.email}
          </h1>
          {account.label && (
            <p className="text-sm text-stone-500">{account.email}</p>
          )}
        </header>
        {stats && <Quota stats={stats} />}
        <AiKeySection />
      </div>
    </div>
  );
}
