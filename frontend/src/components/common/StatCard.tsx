import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  badge?: {
    text: string;
    variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  };
  highlightColor?: string;
}

export const StatCard: React.FC<StatCardProps> = ({ label, value, subtext, icon: Icon, badge }) => {
  const badgeStyles = {
    success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    warning: 'bg-amber-50 text-amber-700 border-amber-200',
    danger: 'bg-rose-50 text-rose-700 border-rose-200',
    info: 'bg-blue-50 text-blue-700 border-blue-200',
    neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  };

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        {Icon && <Icon className="w-4 h-4 text-slate-400" strokeWidth={1.7} />}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <div className="text-2xl font-semibold text-slate-900 tracking-tight tabular-nums">{value}</div>
        {badge && <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${badgeStyles[badge.variant]}`}>{badge.text}</span>}
      </div>
      {subtext && <p className="text-xs text-slate-500 mt-2 leading-relaxed">{subtext}</p>}
    </section>
  );
};
