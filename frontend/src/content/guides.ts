import type { Role } from '../types/api';

type Audience = 'everyone' | 'admins' | 'owner';

export interface Guide {
  // Its file in the repository's docs/ folder, and its address:
  // #docs/<id>.
  id: string;
  title: string;
  group: string;
  audience: Audience;
}

// Adding a guide is one line here and a file in docs/. Who sees one is
// about focus, not secrecy: the files are in the repository.
const GUIDES: Guide[] = [
  {
    id: 'getting-started',
    title: 'Getting started',
    group: 'Start here',
    audience: 'everyone',
  },
  {
    id: 'cluster-agent',
    title: 'Running jobs on your cluster',
    group: 'Run on your cluster',
    audience: 'everyone',
  },
  {
    id: 'quantum-espresso',
    title: 'Quantum ESPRESSO',
    group: 'Workflows',
    audience: 'everyone',
  },
  {
    id: 'ahc-pipeline',
    title: 'Anomalous Hall pipeline',
    group: 'Workflows',
    audience: 'everyone',
  },
  {
    id: 'labs',
    title: 'Labs, roles and workflows',
    group: 'People',
    audience: 'admins',
  },
  {
    id: 'deploy',
    title: 'Putting AtomField on a server',
    group: 'Running a server',
    audience: 'owner',
  },
  {
    id: 'releases',
    title: 'Publishing the scripts',
    group: 'Running a server',
    audience: 'owner',
  },
];

// One chunk per guide, fetched when it is opened.
const GUIDE_FILES = import.meta.glob<string>('@docs/*.md', {
  query: '?raw',
  import: 'default',
});

function mayRead(guide: Guide, role: Role | null): boolean {
  if (guide.audience === 'owner') return role === 'owner';
  if (guide.audience === 'admins') {
    return role === 'owner' || role === 'admin';
  }
  return true;
}

/**
 * The guides someone may read, in order; `role` is null when signed out.
 */
export function guidesFor(role: Role | null): Guide[] {
  return GUIDES.filter((guide) => mayRead(guide, role));
}

/**
 * Whether a guide of this id exists, for anyone at all.
 */
export function isGuide(id: string): boolean {
  return GUIDES.some((guide) => guide.id === id);
}

/**
 * The text of a guide's file.
 */
export function loadGuide(id: string): Promise<string> {
  const file = Object.keys(GUIDE_FILES).find((path) =>
    path.endsWith(`/${id}.md`)
  );
  return file
    ? GUIDE_FILES[file]()
    : Promise.reject(new Error(`No file for guide ${id}`));
}
