import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ErrorMessageProps {
  message: string;
  className?: string;
}

export default function ErrorMessage({ message, className }: ErrorMessageProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-card border border-conviction-sell/30",
        "bg-conviction-sell/5 px-4 py-3 text-sm text-conviction-sell",
        className
      )}
      role="alert"
    >
      <AlertCircle size={16} aria-hidden />
      <span>{message}</span>
    </div>
  );
}
