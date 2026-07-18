/**
 * Plan 138 — barrel de primitivas UI. Contrato congelado en plan 138 §10.2.
 * NOTA: EmptyState (components/EmptyState.tsx) NO se re-exporta a propósito:
 * su adopción/movida es decisión del plan 140. El Toast unificado es contrato
 * del plan 135 F5 — PROHIBIDO crearlo acá.
 */
export { default as Button, buttonPartKeys } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";
export { default as IconButton, iconButtonPartKeys } from "./IconButton";
export type { IconButtonProps, IconButtonVariant, IconButtonSize } from "./IconButton";
export { default as StatusChip, chipPartKeys } from "./StatusChip";
export type { StatusChipProps, StatusTone, ChipSize } from "./StatusChip";
export { default as Card, cardPartKeys } from "./Card";
export type { CardProps, CardPadding } from "./Card";
export { default as SectionHeader } from "./SectionHeader";
export type { SectionHeaderProps } from "./SectionHeader";
export { default as Tabs, tabPartKeys } from "./Tabs";
export type { TabsProps, TabItem, TabsSize } from "./Tabs";
export { default as Skeleton, skeletonStyle } from "./Skeleton";
export type { SkeletonProps } from "./Skeleton";
export { default as Spinner, spinnerStyle } from "./Spinner";
export type { SpinnerProps } from "./Spinner";

// Plan 162 — primitivas de formulario (aditivo al contrato 138 §10.2).
export { default as Field, fieldControlProps, firstErrorFieldId } from "./Field";
export type { FieldProps, FieldControlProps } from "./Field";
export { default as Input, inputPartKeys } from "./Input";
export type { InputProps } from "./Input";
export { default as Select, selectPartKeys } from "./Select";
export type { SelectProps } from "./Select";
export { default as Textarea, textareaPartKeys } from "./Textarea";
export type { TextareaProps } from "./Textarea";
export { default as Checkbox, checkboxPartKeys } from "./Checkbox";
export type { CheckboxProps } from "./Checkbox";

// Plan 164 — primitiva Dialog canónica + derivados de marca + hooks
// promise-based (aditivo; las 13 primitivas de arriba no se tocan).
export { default as Dialog } from "./Dialog";
export type { DialogProps } from "./Dialog";
export { default as ConfirmDialog } from "./ConfirmDialog";
export type { ConfirmDialogProps } from "./ConfirmDialog";
export { default as AlertDialog } from "./AlertDialog";
export type { AlertDialogProps } from "./AlertDialog";
export { default as PromptDialog } from "./PromptDialog";
export type { PromptDialogProps } from "./PromptDialog";
export { default as DialogHost, useConfirm, useAlert, useTextPrompt } from "./DialogHost";
export type { ConfirmOpts, AlertOpts, TextPromptOpts } from "./DialogHost";
