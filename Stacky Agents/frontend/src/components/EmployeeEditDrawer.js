import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { getAgentAvatar, setAgentAvatar, getAgentNickname, setAgentNickname, getAgentRole, setAgentRole, removePinnedAgent, } from "../services/preferences";
import AvatarPicker from "./AvatarPicker";
import PixelAvatar from "./PixelAvatar";
import styles from "./EmployeeEditDrawer.module.css";
export default function EmployeeEditDrawer({ filename, agent, onClose, onRemoved }) {
    const defaultName = agent?.name ?? filename.replace(/\.agent\.md$/i, "");
    const defaultRole = agent?.description?.split(".")[0] ?? "Agente VS Code";
    const [nickname, setNickname] = useState(getAgentNickname(filename) ?? "");
    const [role, setRole] = useState(getAgentRole(filename) ?? "");
    const [avatar, setAvatar] = useState(getAgentAvatar(filename));
    const [confirmRemove, setConfirmRemove] = useState(false);
    function handleSave() {
        if (avatar)
            setAgentAvatar(filename, avatar);
        setAgentNickname(filename, nickname.trim() || defaultName);
        setAgentRole(filename, role.trim() || defaultRole);
        onClose();
    }
    function handleRemove() {
        removePinnedAgent(filename);
        onRemoved();
    }
    return (_jsx("div", { className: styles.overlay, onClick: (e) => e.target === e.currentTarget && onClose(), children: _jsxs("div", { className: styles.drawer, children: [_jsxs("div", { className: styles.header, children: [_jsx(PixelAvatar, { value: avatar, size: "md", name: nickname || defaultName }), _jsxs("div", { className: styles.headerText, children: [_jsx("h2", { className: styles.title, children: "Editar empleado" }), _jsx("span", { className: styles.filename, children: filename })] }), _jsx("button", { className: styles.closeBtn, onClick: onClose, title: "Cerrar", children: "\u2715" })] }), _jsxs("div", { className: styles.body, children: [_jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Apodo" }), _jsx("input", { className: styles.input, type: "text", placeholder: defaultName, value: nickname, onChange: (e) => setNickname(e.target.value) })] }), _jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Rol" }), _jsx("input", { className: styles.input, type: "text", placeholder: defaultRole, value: role, onChange: (e) => setRole(e.target.value) })] }), _jsxs("div", { className: styles.field, children: [_jsx("label", { className: styles.label, children: "Avatar" }), _jsx(AvatarPicker, { value: avatar, onChange: (v) => setAvatar(v) })] })] }), _jsxs("div", { className: styles.footer, children: [confirmRemove ? (_jsxs("div", { className: styles.confirmRow, children: [_jsx("span", { className: styles.confirmText, children: "\u00BFQuitar del equipo?" }), _jsx("button", { className: styles.cancelBtn, onClick: () => setConfirmRemove(false), children: "No" }), _jsx("button", { className: styles.dangerBtn, onClick: handleRemove, children: "S\u00ED, quitar" })] })) : (_jsx("button", { className: styles.removeBtn, onClick: () => setConfirmRemove(true), children: "\uD83D\uDDD1\uFE0F Quitar del equipo" })), _jsxs("div", { className: styles.mainActions, children: [_jsx("button", { className: styles.cancelBtn, onClick: onClose, children: "Cancelar" }), _jsx("button", { className: styles.saveBtn, onClick: handleSave, children: "Guardar" })] })] })] }) }));
}
