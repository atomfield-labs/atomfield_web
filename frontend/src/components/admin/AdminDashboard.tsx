import React, { useState, useEffect } from 'react';
import {
  Users,
  Activity,
  CheckCircle2,
  Clock,
  Search,
  RefreshCw,
  ArrowLeft,
  Shield,
  Sliders,
  X,
  AlertTriangle,
} from 'lucide-react';
import { adminService } from '../../api/services';
import type {
  AdminStatsResponse,
  AdminUserSummary,
} from '../../types/api';

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStatsResponse | null>(null);
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Quota Edit Modal state
  const [selectedUser, setSelectedUser] = useState<AdminUserSummary | null>(null);
  const [newLimit, setNewLimit] = useState<number>(100);
  const [resetUsed, setResetUsed] = useState<boolean>(false);
  const [isUpdatingQuota, setIsUpdatingQuota] = useState<boolean>(false);

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [statsData, usersData] = await Promise.all([
        adminService.getAdminStats(),
        adminService.getAdminUsers(),
      ]);
      setStats(statsData);
      setUsers(usersData.users);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        'Unable to load administrator data. Please check your credentials.';
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleOpenQuotaModal = (user: AdminUserSummary) => {
    setSelectedUser(user);
    setNewLimit(user.quota_limit);
    setResetUsed(false);
  };

  const handleSaveQuota = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    setIsUpdatingQuota(true);
    try {
      const updated = await adminService.updateUserQuota(
        selectedUser.id,
        newLimit,
        resetUsed
      );
      setUsers((prev) =>
        prev.map((u) => (u.id === updated.id ? updated : u))
      );
      setSelectedUser(null);
    } catch (err: any) {
      alert(
        err?.response?.data?.detail || 'Failed to update user calculation quota.'
      );
    } finally {
      setIsUpdatingQuota(false);
    }
  };

  const filteredUsers = users.filter((u) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    const labelMatch = (u.label || '').toLowerCase().includes(query);
    const prefixMatch = u.key_prefix.toLowerCase().includes(query);
    return labelMatch || prefixMatch;
  });

  const formatRuntime = (totalSeconds: number) => {
    if (totalSeconds < 60) {
      return `${totalSeconds.toFixed(1)}s`;
    }
    const mins = Math.floor(totalSeconds / 60);
    const secs = Math.round(totalSeconds % 60);
    return `${mins}m ${secs}s`;
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return 'Never';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return 'Recent';
    }
  };

  const successRate =
    stats && stats.total_jobs > 0
      ? ((stats.success_jobs / stats.total_jobs) * 100).toFixed(1)
      : '100.0';

  if (error) {
    return (
      <div className="w-full min-h-screen bg-slate-50 p-8 pt-24 flex items-center justify-center">
        <div className="bg-white border border-slate-200 rounded-xl p-8 max-w-md w-full text-center shadow-sm">
          <div className="w-12 h-12 bg-red-50 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4 border border-red-200">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-slate-800 mb-2">Access Restricted</h2>
          <p className="text-sm text-slate-600 mb-6">{error}</p>
          <a
            href="#dashboard"
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Sessions
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-slate-50 p-8 pt-24">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 mb-1.5">
              <a
                href="#dashboard"
                className="text-slate-400 hover:text-slate-700 transition-colors"
                title="Back to Sessions"
              >
                <ArrowLeft className="w-5 h-5" />
              </a>
              <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                <Shield className="w-6 h-6 text-orange-600" />
                Cluster Administration
              </h1>
            </div>
            <p className="text-sm text-slate-500 ml-7">
              Global compute metrics and per-user calculation tracking.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={fetchData}
              disabled={isLoading}
              className="px-3.5 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-xs flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 text-slate-500 ${
                  isLoading ? 'animate-spin text-orange-500' : ''
                }`}
              />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Global Platform Statistics Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Registered Users */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Total Users
              </span>
              <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900">
              {isLoading && !stats ? '...' : stats?.total_users ?? 0}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Active API keys on cluster
            </div>
          </div>

          {/* Calculations Submitted */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Total Jobs
              </span>
              <div className="w-8 h-8 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center">
                <Activity className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900">
              {isLoading && !stats ? '...' : stats?.total_jobs ?? 0}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Calculations executed cluster-wide
            </div>
          </div>

          {/* Success Rate */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Success Rate
              </span>
              <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <CheckCircle2 className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900">
              {isLoading && !stats ? '...' : `${successRate}%`}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              {stats?.success_jobs ?? 0} passed / {stats?.failed_jobs ?? 0} failed
            </div>
          </div>

          {/* Total Compute Time */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Total Runtime
              </span>
              <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                <Clock className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold text-slate-900">
              {isLoading && !stats
                ? '...'
                : formatRuntime(stats?.total_compute_seconds ?? 0)}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Cumulative worker calculation time
            </div>
          </div>
        </div>

        {/* Per-User Tracking Section */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
          {/* Table Header & Search Filter */}
          <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-slate-900">
                User Job Statistics
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Breakdown of job submissions, error rates, and resource utilization per API key.
              </p>
            </div>

            <div className="relative w-full sm:w-72">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search user or key prefix..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-orange-500 focus:bg-white transition-colors"
              />
            </div>
          </div>

          {/* Users Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  <th className="py-3 px-5">User / Label</th>
                  <th className="py-3 px-4">Key Prefix</th>
                  <th className="py-3 px-4 text-center">Total Jobs</th>
                  <th className="py-3 px-4 text-center">Status Breakdown</th>
                  <th className="py-3 px-4">Compute Time</th>
                  <th className="py-3 px-4">Quota Used</th>
                  <th className="py-3 px-4">Last Active</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs">
                {isLoading && users.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="py-12 text-center text-slate-400 text-xs"
                    >
                      Loading user usage metrics...
                    </td>
                  </tr>
                ) : filteredUsers.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="py-12 text-center text-slate-400 text-xs"
                    >
                      No user accounts found matching &quot;{searchQuery}&quot;.
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((user) => {
                    const usagePercent =
                      user.quota_limit > 0
                        ? Math.min(
                            100,
                            Math.round((user.quota_used / user.quota_limit) * 100)
                          )
                        : 0;

                    const isClusterAdmin =
                      user.label === 'Cluster Administrator';

                    return (
                      <tr
                        key={user.id}
                        className="hover:bg-slate-50/70 transition-colors"
                      >
                        {/* User / Label */}
                        <td className="py-3.5 px-5">
                          <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                            {user.label || (
                              <span className="text-slate-400 font-normal italic">
                                Anonymous User
                              </span>
                            )}
                            {isClusterAdmin && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-700 border border-orange-200">
                                ADMIN
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Key Prefix */}
                        <td className="py-3.5 px-4 font-mono text-[11px] text-slate-600">
                          <span className="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                            {user.key_prefix}
                          </span>
                        </td>

                        {/* Total Jobs */}
                        <td className="py-3.5 px-4 text-center font-bold text-slate-800">
                          {user.total_jobs}
                        </td>

                        {/* Status Breakdown */}
                        <td className="py-3.5 px-4 text-center">
                          <div className="inline-flex items-center gap-1 font-mono text-[11px]">
                            <span
                              title={`${user.success_jobs} successful jobs`}
                              className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold"
                            >
                              {user.success_jobs}✓
                            </span>
                            <span
                              title={`${user.failed_jobs} failed jobs`}
                              className="px-1.5 py-0.5 rounded bg-red-50 text-red-700 border border-red-200 font-semibold"
                            >
                              {user.failed_jobs}✗
                            </span>
                            {user.running_jobs > 0 && (
                              <span
                                title={`${user.running_jobs} currently running`}
                                className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 font-semibold animate-pulse"
                              >
                                {user.running_jobs}⚡
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Compute Time */}
                        <td className="py-3.5 px-4 font-mono text-slate-700">
                          {formatRuntime(user.total_compute_seconds)}
                        </td>

                        {/* Quota Used */}
                        <td className="py-3.5 px-4">
                          <div className="w-28 space-y-1">
                            <div className="flex items-center justify-between text-[11px] text-slate-600">
                              <span>
                                {user.quota_used} / {user.quota_limit}
                              </span>
                              <span className="text-slate-400 font-mono">
                                {usagePercent}%
                              </span>
                            </div>
                            <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full transition-all duration-300 ${
                                  usagePercent >= 90
                                    ? 'bg-red-500'
                                    : usagePercent >= 70
                                    ? 'bg-amber-500'
                                    : 'bg-emerald-500'
                                }`}
                                style={{ width: `${usagePercent}%` }}
                              />
                            </div>
                          </div>
                        </td>

                        {/* Last Active */}
                        <td className="py-3.5 px-4 text-slate-500 text-[11px]">
                          {formatDate(user.last_used_at)}
                        </td>

                        {/* Actions */}
                        <td className="py-3.5 px-4 text-right">
                          <button
                            onClick={() => handleOpenQuotaModal(user)}
                            className="px-2.5 py-1 text-[11px] font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded shadow-2xs transition-colors inline-flex items-center gap-1 cursor-pointer"
                          >
                            <Sliders className="w-3 h-3 text-slate-500" />
                            <span>Adjust Quota</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Adjust Quota Modal */}
      {selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-sm w-full p-6">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-orange-600" />
                <h3 className="text-sm font-bold text-slate-800">
                  Adjust Quota
                </h3>
              </div>
              <button
                onClick={() => setSelectedUser(null)}
                className="text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mb-4">
              <div className="text-xs text-slate-500">User Identity</div>
              <div className="text-sm font-semibold text-slate-800 mt-0.5">
                {selectedUser.label || 'Anonymous User'}
              </div>
              <div className="font-mono text-[11px] text-slate-500 mt-0.5">
                Key prefix: {selectedUser.key_prefix}
              </div>
            </div>

            <form onSubmit={handleSaveQuota} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  New Quota Limit (Calculations)
                </label>
                <input
                  type="number"
                  min="0"
                  max="1000000"
                  value={newLimit}
                  onChange={(e) => setNewLimit(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg text-slate-800 focus:outline-none focus:ring-1 focus:ring-orange-500 focus:bg-white"
                  required
                />
                <div className="text-[11px] text-slate-400 mt-1">
                  Current: {selectedUser.quota_limit} calculations
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="resetUsed"
                  checked={resetUsed}
                  onChange={(e) => setResetUsed(e.target.checked)}
                  className="rounded text-orange-600 focus:ring-orange-500 cursor-pointer"
                />
                <label
                  htmlFor="resetUsed"
                  className="text-xs text-slate-700 cursor-pointer select-none"
                >
                  Reset used calculations to 0 (was {selectedUser.quota_used})
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setSelectedUser(null)}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isUpdatingQuota}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-lg shadow-xs transition-colors cursor-pointer disabled:opacity-50"
                >
                  {isUpdatingQuota ? 'Updating...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
