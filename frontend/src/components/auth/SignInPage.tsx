import { useState } from 'react';
import { useAccount, type SignInProblem } from '../../hooks/useAccount';

const PROBLEM_TEXT: Record<SignInProblem, string> = {
  expired: 'That sign-in took too long. Please try again.',
  denied: 'Sign-in was cancelled.',
  outside: 'Use your institute Google account.',
  disabled: 'Your account is turned off. Ask the administrator.',
  failed: 'Sign-in failed. Please try again.',
  unavailable: "Sign-in isn't set up on this server yet.",
  busy: 'Too many attempts. Wait a minute, then try again.',
};

// Google's "G" in its own colours, as Google's sign-in guidelines ask.
const GOOGLE_G = [
  {
    fill: '#EA4335',
    d:
      'M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0' +
      ' 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5' +
      ' 24 9.5z',
  },
  {
    fill: '#4285F4',
    d:
      'M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96' +
      '-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z',
  },
  {
    fill: '#FBBC05',
    d:
      'M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98' +
      '-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97' +
      '-6.19z',
  },
  {
    fill: '#34A853',
    d:
      'M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3' +
      '-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62' +
      ' 14.62 48 24 48z',
  },
];

// An imaginary pipeline, drawn rather than real: three steps done
// (green), one running (blue, ringed in orange), one waiting.
const SKETCH_STEPS = [
  { x: 0, y: 96, dot: '#4ADE80' },
  { x: 120, y: 40, dot: '#4ADE80' },
  { x: 120, y: 152, dot: '#4ADE80' },
  { x: 240, y: 96, dot: '#60A5FA', running: true },
  { x: 360, y: 96, dot: '#57534E', waiting: true },
];
const SKETCH_LINKS = [
  'M72 110C96 110 96 54 120 54',
  'M72 110C96 110 96 166 120 166',
  'M192 54C216 54 216 110 240 110',
  'M192 166C216 166 216 110 240 110',
  'M312 110H360',
];

const BRAND_PANEL = [
  'flex-[1_1_520px] flex flex-col justify-between gap-10 p-10',
  'bg-stone-900 text-stone-100',
].join(' ');
const GOOGLE_BUTTON = [
  'h-12 w-full flex items-center justify-center gap-3 rounded-lg',
  'border border-[#747775] bg-white text-[#1F1F1F] text-sm font-medium',
  'hover:bg-stone-50 disabled:opacity-60 cursor-pointer',
  'focus-visible:outline-none focus-visible:ring-2',
  'focus-visible:ring-orange-600/40',
].join(' ');

/**
 * The running step is outlined in orange, a waiting one faintly.
 */
function stepOutline(step: (typeof SKETCH_STEPS)[number]): string {
  if (step.running) return '#FB923C';
  return step.waiting ? '#44403C' : '#3A3531';
}

function GoogleMark() {
  return (
    <svg
      aria-hidden="true"
      width="18"
      height="18"
      viewBox="0 0 48 48"
    >
      {GOOGLE_G.map((part) => (
        <path key={part.fill} fill={part.fill} d={part.d} />
      ))}
    </svg>
  );
}

function AtomMark() {
  return (
    <svg
      aria-hidden="true"
      width="26"
      height="26"
      viewBox="0 0 32 32"
      fill="none"
      stroke="#FB923C"
      strokeWidth="1.8"
    >
      {[0, 60, 120].map((angle) => (
        <ellipse
          key={angle}
          cx="16"
          cy="16"
          rx="13"
          ry="5.2"
          transform={`rotate(${angle} 16 16)`}
        />
      ))}
      <circle cx="16" cy="16" r="2.2" fill="#FB923C" stroke="none" />
    </svg>
  );
}

function PipelineSketch() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 432 220"
      className="w-full max-w-[432px] overflow-visible"
    >
      {SKETCH_LINKS.map((link) => (
        <path
          key={link}
          d={link}
          fill="none"
          stroke="#44403C"
          strokeWidth="1.5"
        />
      ))}
      {SKETCH_STEPS.map((step) => (
        <g key={`${step.x}-${step.y}`}>
          {step.running && (
            <rect
              x={step.x - 4}
              y={step.y - 4}
              width="80"
              height="36"
              rx="12"
              fill="rgba(251,146,60,0.16)"
            />
          )}
          <rect
            x={step.x}
            y={step.y}
            width="72"
            height="28"
            rx="8"
            fill={step.waiting ? 'none' : '#26221F'}
            stroke={stepOutline(step)}
            strokeWidth={step.running ? 1.5 : 1}
            strokeDasharray={step.waiting ? '4 3' : undefined}
          />
          <circle cx={step.x + 13} cy={step.y + 14} r="3" fill={step.dot} />
        </g>
      ))}
    </svg>
  );
}

function BrandPanel() {
  return (
    <section className={BRAND_PANEL}>
      <div className="flex items-center gap-2.5">
        <AtomMark />
        <span className="text-[17px] font-semibold">AtomField</span>
      </div>
      <PipelineSketch />
      <p className="text-[22px] font-medium tracking-tight">
        Scientific pipelines, run anywhere.
      </p>
    </section>
  );
}

/**
 * The one way in: continue with an institute Google account.
 */
export default function SignInPage() {
  const { state, signIn } = useAccount();
  const [leaving, setLeaving] = useState(false);
  const problem = state.status === 'signed-out' ? state.problem : null;

  const continueWithGoogle = () => {
    setLeaving(true);
    signIn();
  };

  return (
    <div className="min-h-screen flex flex-wrap bg-white text-stone-900">
      <BrandPanel />
      <main className="flex-[1_1_420px] flex px-8 py-12">
        <div className="m-auto w-full max-w-[340px] flex flex-col gap-5">
          <h1 className="text-[26px] font-semibold tracking-tight">Sign in</h1>
          <button
            type="button"
            onClick={continueWithGoogle}
            disabled={leaving}
            className={GOOGLE_BUTTON}
          >
            <GoogleMark />
            <span>Continue with Google</span>
          </button>
          {problem ? (
            <p role="alert" className="text-[13px] text-red-700">
              {PROBLEM_TEXT[problem] ?? PROBLEM_TEXT.failed}
            </p>
          ) : (
            <p className="text-[13px] text-stone-500">
              Use your institute account.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
