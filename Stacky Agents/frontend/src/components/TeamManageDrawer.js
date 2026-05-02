import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { getPinnedAgents, addPinnedAgent, removePinnedAgent, getAgentAvatar, setAgentAvatar, getAgentNickname, setAgentNickname, getAgentRole, setAgentRole, } from "../services/preferences";
import PixelAvatar from "./PixelAvatar";
import AvatarPicker from "./AvatarPicker";
import styles from "./TeamManageDrawer.module.css";
export default function TeamManageDrawer({ allAgents, onClose }) {
    const [pinned, setPinned] = useState(() => getPinnedAgents());
    // null = list view · PendingAdd = centered config modal
    const [pendingAdd, setPendingAdd] = useState(null);
    // Close config modal with Escape
    useEffect(() => {
        if (!pendingAdd)
            return;
        const handler = (e) => { if (e.key === "Escape")
            setPendingAdd(null); };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [pendingAdd]);
    function isInTeam(filename) {
        return pinned.includes(filename);
    }
    function handleSelectForAdd(agent) {
        if (isInTeam(agent.filename)) {
            removePinnedAgent(agent.filename);
            setPinned(getPinnedAgents());
            return;
        }
        setPendingAdd({
            filename: agent.filename,
            agentName: agent.name,
            avatar: getAgentAvatar(agent.filename),
            nickname: getAgentNickname(agent.filename) ?? "",
            role: getAgentRole(agent.filename) ?? "",
        });
    }
    function handleConfirmAdd() {
        if (!pendingAdd)
            return;
        if (pendingAdd.avatar)
            setAgentAvatar(pendingAdd.filename, pendingAdd.avatar);
        if (pendingAdd.nickname.trim())
            setAgentNickname(pendingAdd.filename, pendingAdd.nickname.trim());
        if (pendingAdd.role.trim())
            setAgentRole(pendingAdd.filename, pendingAdd.role.trim());
        addPinnedAgent(pendingAdd.filename);
        setPinned(getPinnedAgents());
        setPendingAdd(null);
    }
    return (_jsxs(_Fragment, { children: [_jsx("div", { className: styles.overlay, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.drawer, children: [_jsxs("div", { className: styles.header, children: [_jsx("h2", { className: styles.title, children: "Agentes disponibles en VS Code" }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), _jsxs("p", { className: styles.hint, children: ["\uD83D\uDCC1 Fuente: ", _jsx("code", { children: "%APPDATA%/Code/User/prompts" })] }), allAgents.length === 0 ? (_jsx("div", { className: styles.empty, children: "No se encontraron agentes. Verific\u00E1 que VS Code est\u00E9 corriendo con la extensi\u00F3n Stacky." })) : (_jsx("div", { className: styles.list, children: allAgents.map((agent) => {
                                const inTeam = isInTeam(agent.filename);
                                const avatar = getAgentAvatar(agent.filename);
                                return (_jsxs("div", { className: inTeam ? styles.agentRowDone : styles.agentRow, children: [_jsx(PixelAvatar, { value: avatar, size: "sm", name: agent.name }), _jsxs("div", { className: styles.agentInfo, children: [_jsx("span", { className: styles.agentName, children: agent.name }), _jsx("span", { className: styles.agentDesc, children: agent.description?.slice(0, 80) ?? agent.filename })] }), inTeam && _jsx("span", { className: styles.inTeamBadge, children: "\u2713" }), _jsx("button", { className: inTeam ? styles.removeBtn : styles.addBtn, onClick: () => handleSelectForAdd(agent), children: inTeam ? "Quitar" : "+ Agregar" })] }, agent.filename));
                            }) })), _jsx("div", { className: styles.footer, children: _jsx("button", { className: styles.doneBtn, onClick: onClose, children: "Listo" }) })] }) }), pendingAdd && (_jsx("div", { className: styles.modalBackdrop, onClick: (e) => e.target === e.currentTarget && setPendingAdd(null), children: _jsxs("div", { className: styles.modal, role: "dialog", "aria-modal": "true", children: [_jsx("div", { className: styles.modalAvatar, children: _jsx(PixelAvatar, { value: pendingAdd.avatar, size: "lg", name: pendingAdd.agentName }) }), _jsx("h3", { className: styles.modalAgentName, children: pendingAdd.agentName }), _jsx("p", { className: styles.modalSubtitle, children: "Personaliz\u00E1 tu nuevo empleado" }), _jsxs("div", { className: styles.modalFields, children: [_jsxs("div", { className: styles.modalField, children: [_jsx("label", { className: styles.modalLabel, children: "Apodo" }), _jsx("input", { className: styles.modalInput, placeholder: pendingAdd.agentName, value: pendingAdd.nickname, onChange: (e) => setPendingAdd({ ...pendingAdd, nickname: e.target.value }), autoFocus: true })] }), _jsxs("div", { className: styles.modalField, children: [_jsx("label", { className: styles.modalLabel, children: "Rol" }), _jsx("input", { className: styles.modalInput, placeholder: "ej: Analista Senior", value: pendingAdd.role, onChange: (e) => setPendingAdd({ ...pendingAdd, role: e.target.value }) })] })] }), _jsxs("div", { className: styles.modalPickerSection, children: [_jsx("label", { className: styles.modalLabel, children: "Avatar" }), _jsx(AvatarPicker, { value: pendingAdd.avatar, onChange: (v) => setPendingAdd({ ...pendingAdd, avatar: v }) })] }), _jsxs("div", { className: styles.modalActions, children: [_jsx("button", { className: styles.modalCancelBtn, onClick: () => setPendingAdd(null), children: "Cancelar" }), _jsx("button", { className: styles.modalConfirmBtn, onClick: handleConfirmAdd, children: "\u2713 Agregar al equipo" })] })] }) }))] }));
}
