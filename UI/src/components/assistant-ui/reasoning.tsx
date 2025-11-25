import { BrainIcon, ChevronDownIcon } from "lucide-react";
import { memo, useCallback, useRef, useState, type FC, type PropsWithChildren } from "react";

import {
  useScrollLock,
  useAssistantState,
  type ReasoningMessagePartComponent,
  type ReasoningGroupComponent,
} from "@assistant-ui/react";

import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/utils/utils";

const ANIMATION_DURATION = 200;

/**
 * Root collapsible container that manages open/closed state and scroll lock.
 */
const ReasoningRoot: FC<PropsWithChildren<{ className?: string }>> = ({ className, children }) => {
  const collapsibleRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const lockScroll = useScrollLock(collapsibleRef, ANIMATION_DURATION);

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        lockScroll();
      }
      setIsOpen(open);
    },
    [lockScroll]
  );

  return (
    <Collapsible
      ref={collapsibleRef}
      open={isOpen}
      onOpenChange={handleOpenChange}
      className={cn("mb-4 w-full", className)}
    >
      {children}
    </Collapsible>
  );
};

/**
 * Trigger button for the Reasoning collapsible.
 */
const ReasoningTrigger: FC<{ active: boolean; className?: string }> = ({ active, className }) => (
  <CollapsibleTrigger
    className={cn(
      "group/trigger -mb-2 flex max-w-[75%] items-center gap-2 py-2 text-sm text-gray-500 dark:text-gray-400 transition-colors hover:text-gray-700 dark:hover:text-gray-200",
      className
    )}
  >
    <BrainIcon className="size-4 shrink-0" />
    <span className="relative inline-block leading-none">
      <span>Reasoning</span>
      {active && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 animate-pulse text-blue-500"
        >
          Reasoning
        </span>
      )}
    </span>
    <ChevronDownIcon
      className={cn(
        "mt-0.5 size-4 shrink-0 transition-transform duration-200 ease-out",
        "group-data-[state=closed]/trigger:-rotate-90",
        "group-data-[state=open]/trigger:rotate-0"
      )}
    />
  </CollapsibleTrigger>
);

/**
 * Collapsible content wrapper.
 */
const ReasoningContentWrapper: FC<
  PropsWithChildren<{ className?: string; "aria-busy"?: boolean }>
> = ({ className, children, "aria-busy": ariaBusy }) => (
  <CollapsibleContent
    className={cn(
      "relative overflow-hidden text-sm text-gray-600 dark:text-gray-400",
      "data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down",
      className
    )}
    aria-busy={ariaBusy}
  >
    {children}
  </CollapsibleContent>
);

/**
 * Text content wrapper.
 */
const ReasoningTextWrapper: FC<PropsWithChildren<{ className?: string }>> = ({
  className,
  children,
}) => (
  <div className={cn("relative space-y-4 pt-4 pl-6 leading-relaxed", className)}>{children}</div>
);

/**
 * Renders a single reasoning part's text with markdown support.
 */
const ReasoningImpl: ReasoningMessagePartComponent = () => (
  <MarkdownTextPrimitive
    remarkPlugins={[remarkGfm]}
    className="prose prose-sm dark:prose-invert max-w-none"
  />
);

/**
 * Collapsible wrapper that groups consecutive reasoning parts together.
 */
const ReasoningGroupImpl: ReasoningGroupComponent = ({ children, startIndex, endIndex }) => {
  const isReasoningStreaming = useAssistantState(({ message }) => {
    if (message.status?.type !== "running") return false;
    const lastIndex = message.parts.length - 1;
    if (lastIndex < 0) return false;
    const lastType = message.parts[lastIndex]?.type;
    if (lastType !== "reasoning") return false;
    return lastIndex >= startIndex && lastIndex <= endIndex;
  });

  return (
    <ReasoningRoot>
      <ReasoningTrigger active={isReasoningStreaming} />
      <ReasoningContentWrapper aria-busy={isReasoningStreaming}>
        <ReasoningTextWrapper>{children}</ReasoningTextWrapper>
      </ReasoningContentWrapper>
    </ReasoningRoot>
  );
};

export const Reasoning = memo(ReasoningImpl);
Reasoning.displayName = "Reasoning";

export const ReasoningGroup = memo(ReasoningGroupImpl);
ReasoningGroup.displayName = "ReasoningGroup";
