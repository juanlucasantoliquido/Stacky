import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useAutoFillBlocks } from "../hooks/useAutoFillBlocks";
import AgentSelector from "../components/AgentSelector";
import ExecutionHistory from "../components/ExecutionHistory";
import InputContextEditor from "../components/InputContextEditor";
import LogsPanel from "../components/LogsPanel";
import OutputPanel from "../components/OutputPanel";
import TicketSelector from "../components/TicketSelector";
import TopBar from "../components/TopBar";
import styles from "./Workbench.module.css";
export default function Workbench({ onGoToTeam }) {
    useAutoFillBlocks();
    return (_jsxs("div", { className: styles.app, children: [_jsx(TopBar, { onGoToTeam: onGoToTeam }), _jsxs("div", { className: styles.body, children: [_jsxs("aside", { className: styles.left, children: [_jsx(TicketSelector, {}), _jsx(AgentSelector, {})] }), _jsx("main", { className: styles.center, children: _jsx(InputContextEditor, {}) }), _jsxs("aside", { className: styles.right, children: [_jsx(OutputPanel, {}), _jsx(LogsPanel, {}), _jsx(ExecutionHistory, {})] })] })] }));
}
