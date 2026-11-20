import { CircleCheck, Info, OctagonAlert, TriangleAlert, X } from "lucide-react";
import { Toaster as Sonner } from "sonner";

type ToasterProps = React.ComponentProps<typeof Sonner>;

/*
 * Posição e visual: ver "Avisos" em index.css.
 * Os offsets vêm de variáveis CSS para trocar no breakpoint (md) sem JS:
 * desktop = canto inferior direito, longe do header e do menu de categorias;
 * mobile = acima do TabBar e da barra fixa de compra, com safe-area.
 */
const Toaster = (props: ToasterProps) => {
  return (
    <Sonner
      position="bottom-right"
      visibleToasts={3}
      duration={4000}
      gap={8}
      closeButton
      containerAriaLabel="Avisos"
      style={{ "--width": "400px" } as React.CSSProperties}
      offset={{ bottom: "var(--toast-bottom)", right: "var(--toast-side)" }}
      mobileOffset={{ bottom: "var(--toast-bottom)", left: "var(--toast-side)", right: "var(--toast-side)" }}
      icons={{
        success: <CircleCheck className="size-4" aria-hidden="true" />,
        info: <Info className="size-4" aria-hidden="true" />,
        warning: <TriangleAlert className="size-4" aria-hidden="true" />,
        error: <OctagonAlert className="size-4" aria-hidden="true" />,
        close: <X className="size-4" aria-hidden="true" />,
      }}
      toastOptions={{ closeButtonAriaLabel: "Fechar aviso" }}
      {...props}
    />
  );
};

export { Toaster };
