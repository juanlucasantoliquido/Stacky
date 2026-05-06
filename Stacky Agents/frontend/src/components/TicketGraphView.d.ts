import type { TicketHierarchy, AgentExecution, VsCodeAgent } from "../types";

interface TicketGraphViewProps {
  hierarchy: TicketHierarchy | null;
  onSync: () => void;
  isSyncing: boolean;
  vsCodeAgents?: VsCodeAgent[];
  runningByTicket?: Map<number, AgentExecution>;
}

declare const TicketGraphView: (props: TicketGraphViewProps) => JSX.Element;
export default TicketGraphView;
