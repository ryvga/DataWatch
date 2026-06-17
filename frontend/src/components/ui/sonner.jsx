import { useTheme } from "next-themes"
import { Toaster as Sonner } from "sonner"

const Toaster = ({ ...props }) => {
  const { resolvedTheme } = useTheme()

  return (
    <Sonner
      theme={resolvedTheme}
      position="bottom-right"
      gap={8}
      visibleToasts={4}
      richColors
      closeButton
      className="toaster group"
      toastOptions={{
        duration: 4500,
        classNames: {
          toast:
            "!font-sans !rounded-lg !border !shadow-lg",
          title:
            "!text-sm !font-semibold",
          description:
            "!text-xs !text-muted-foreground",
          actionButton:
            "!text-xs !font-medium",
          cancelButton:
            "!text-xs !font-medium",
          closeButton:
            "!rounded-md !border-border hover:!bg-muted",
          success:
            "!border-emerald-500/20 !bg-emerald-500/5 [&>[data-icon]]:!text-emerald-500",
          error:
            "!border-red-500/20 !bg-red-500/5 [&>[data-icon]]:!text-red-500",
          warning:
            "!border-orange-500/20 !bg-orange-500/5 [&>[data-icon]]:!text-orange-500",
          info:
            "!border-primary/20 !bg-primary/5 [&>[data-icon]]:!text-primary",
        },
      }}
      style={{
        "--normal-bg": "hsl(var(--popover))",
        "--normal-text": "hsl(var(--popover-foreground))",
        "--normal-border": "hsl(var(--border))",
        "--border-radius": "var(--radius)",
        "--font-family": "var(--font-sans)",
        "--toast-min-width": "320px",
      }}
      {...props}
    />
  )
}

export { Toaster }
