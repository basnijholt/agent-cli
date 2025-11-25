import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";
import { forwardRef } from "react";

const Collapsible = forwardRef<
  React.ComponentRef<typeof CollapsiblePrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.Root>
>(({ ...props }, ref) => (
  <CollapsiblePrimitive.Root ref={ref} data-slot="collapsible" {...props} />
));
Collapsible.displayName = "Collapsible";

const CollapsibleTrigger = forwardRef<
  React.ComponentRef<typeof CollapsiblePrimitive.CollapsibleTrigger>,
  React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.CollapsibleTrigger>
>(({ ...props }, ref) => (
  <CollapsiblePrimitive.CollapsibleTrigger
    ref={ref}
    data-slot="collapsible-trigger"
    {...props}
  />
));
CollapsibleTrigger.displayName = "CollapsibleTrigger";

const CollapsibleContent = forwardRef<
  React.ComponentRef<typeof CollapsiblePrimitive.CollapsibleContent>,
  React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.CollapsibleContent>
>(({ ...props }, ref) => (
  <CollapsiblePrimitive.CollapsibleContent
    ref={ref}
    data-slot="collapsible-content"
    {...props}
  />
));
CollapsibleContent.displayName = "CollapsibleContent";

export { Collapsible, CollapsibleTrigger, CollapsibleContent };
