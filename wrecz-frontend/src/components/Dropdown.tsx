import { useEffect, useState, type ReactNode } from "react";

type DropdownProps = {
  open: boolean;
  children: ReactNode;
  className?: string;
};

export default function Dropdown({ open, children, className = "" }: DropdownProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(open);

  useEffect(() => {
    if (open) {
      setMounted(true);
      const frame = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(frame);
    }

    setVisible(false);
    const timeout = window.setTimeout(() => setMounted(false), 150);
    return () => window.clearTimeout(timeout);
  }, [open]);

  if (!mounted) return null;

  return (
    <div
      className={`wrecz-dropdown ${visible ? "is-visible" : ""} ${className}`}
      onClick={(event) => event.stopPropagation()}
    >
      {children}
    </div>
  );
}
