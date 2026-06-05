import { useTheme } from "next-themes"
import { Toaster as Sonner } from "sonner"

const Toaster = ({ ...props }) => {
  const { resolvedTheme } = useTheme()

  return (
    <Sonner
      theme={resolvedTheme}
      position="top-right"
      gap={8}
      visibleToasts={5}
      className="toaster group"
      toastOptions={{
        duration: 4500,
        classNames: {
          toast: "!font-sans",
        },
      }}
      style={{
        "--normal-bg": "hsl(var(--popover))",
        "--normal-text": "hsl(var(--popover-foreground))",
        "--normal-border": "hsl(var(--border))",
        "--border-radius": "var(--radius)",
        "--font-family": "var(--font-sans)",
      }}
      {...props}
    />
  )
}

export { Toaster }
