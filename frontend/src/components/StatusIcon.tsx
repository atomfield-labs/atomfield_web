import {
  Circle,
  CircleCheck,
  CircleSlash,
  CircleX,
  Clock,
  LoaderCircle,
} from 'lucide-react';
import { STATUS_TEXT, statusLook } from '../utils/jobStatus';

const ICONS = {
  none: { Icon: Circle, className: 'text-stone-300' },
  waiting: { Icon: Clock, className: 'text-stone-400' },
  running: { Icon: LoaderCircle, className: 'text-blue-600 animate-spin' },
  done: { Icon: CircleCheck, className: 'text-green-600' },
  failed: { Icon: CircleX, className: 'text-red-600' },
  stopped: { Icon: CircleSlash, className: 'text-stone-400' },
};

/**
 * A step's status as one small icon; the colour carries the meaning
 * (green done, blue running, grey waiting, red failed).
 */
export default function StatusIcon({
  status,
  size = 16,
}: {
  status?: string | null;
  size?: number;
}) {
  const look = statusLook(status);
  const { Icon, className } = ICONS[look];
  return (
    <Icon
      role="img"
      aria-label={STATUS_TEXT[look]}
      size={size}
      strokeWidth={2.2}
      className={`shrink-0 ${className}`}
    />
  );
}
