import * as React from "react";

export interface NodeErrorBoundaryProps {
  adoId?: number;
  children?: React.ReactNode;
}

export class NodeErrorBoundary extends React.Component<
  NodeErrorBoundaryProps,
  { hasError: boolean; error: Error | null }
> {}

declare const TicketGraphView: React.ComponentType<any>;
export default TicketGraphView;
