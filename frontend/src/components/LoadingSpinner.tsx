import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  label?: string;
}

const SIZE_CLASSES = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-10 w-10" };

export default function LoadingSpinner({
  className,
  size = "md",
  label = "Loading…",
}: LoadingSpinnerProps) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-3 py-12 text-text-muted", className)}
      role="status"
      aria-label={label}
    >
      <svg
        className={cn("animate-spin", SIZE_CLASSES[size])}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden
      >
        <circle
          className="opacity-25"
          cx="12" cy="12" r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
        />
      </svg>
      <span className="text-sm">{label}</span>
    </div>
  );
}
