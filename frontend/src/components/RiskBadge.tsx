import { Shield, AlertTriangle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface RiskBadgeProps {
  riskLevel: string | null;
  riskScore?: number | null;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}

const RISK_CONFIG = {
  Low: {
    color: "text-success",
    bgColor: "bg-success/10",
    borderColor: "border-success/30",
    icon: Shield,
    label: "Low Risk",
  },
  Medium: {
    color: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-warning/30",
    icon: AlertTriangle,
    label: "Medium Risk",
  },
  High: {
    color: "text-danger",
    bgColor: "bg-danger/10",
    borderColor: "border-danger/30",
    icon: AlertCircle,
    label: "High Risk",
  },
};

export default function RiskBadge({
  riskLevel,
  riskScore,
  size = "md",
  showLabel = true,
  className,
}: RiskBadgeProps) {
  if (!riskLevel || !(riskLevel in RISK_CONFIG)) {
    return null;
  }

  const config = RISK_CONFIG[riskLevel as keyof typeof RISK_CONFIG];
  const Icon = config.icon;

  const sizeClasses = {
    sm: "text-2xs px-1.5 py-0.5",
    md: "text-xs px-2 py-1",
    lg: "text-sm px-3 py-1.5",
  };

  const iconSizes = {
    sm: 10,
    md: 12,
    lg: 14,
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        "transition-all duration-200",
        config.bgColor,
        config.borderColor,
        config.color,
        sizeClasses[size],
        className
      )}
      title={riskScore != null ? `Risk Score: ${riskScore.toFixed(1)}` : undefined}
    >
      <Icon size={iconSizes[size]} aria-hidden />
      {showLabel && <span>{config.label}</span>}
    </div>
  );
}
