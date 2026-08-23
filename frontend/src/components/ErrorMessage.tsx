import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export default function ErrorMessage({ message, className }: { message: string; className?: string }) {
  return (
    <div className={cn("surface-card p-6 flex flex-col items-center gap-2 text-center", className)}>
      <AlertTriangle size={20} className="text-down" />
      <p className="text-sm text-ink-dim">{message}</p>
    </div>
  );
}
