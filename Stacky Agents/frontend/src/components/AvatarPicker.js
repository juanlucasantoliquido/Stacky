import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useRef, useState } from "react";
import { GALLERY_AVATARS } from "../services/avatarGallery";
import styles from "./AvatarPicker.module.css";
const CATEGORIES = [
    { key: "dev", label: "Dev" },
    { key: "analyst", label: "Analista" },
    { key: "qa", label: "QA" },
    { key: "pm", label: "PM/TL" },
    { key: "ops", label: "Ops/BD" },
    { key: "design", label: "Diseño" },
    { key: "special", label: "Especial" },
];
export default function AvatarPicker({ value, onChange }) {
    const [filter, setFilter] = useState("all");
    const [preview, setPreview] = useState(null);
    const [uploading, setUploading] = useState(false);
    const fileRef = useRef(null);
    const filtered = filter === "all" ? GALLERY_AVATARS : GALLERY_AVATARS.filter((a) => a.category === filter);
    function handleFileUpload(e) {
        const file = e.target.files?.[0];
        if (!file)
            return;
        setUploading(true);
        const reader = new FileReader();
        reader.onload = (ev) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width = 64;
                canvas.height = 64;
                const ctx = canvas.getContext("2d");
                // nearest-neighbor pixelated scaling
                ctx.imageSmoothingEnabled = false;
                ctx.drawImage(img, 0, 0, 64, 64);
                const base64 = canvas.toDataURL("image/png");
                setPreview(base64);
                onChange(base64);
                setUploading(false);
            };
            img.src = ev.target?.result;
        };
        reader.readAsDataURL(file);
        // reset so same file can be re-selected
        e.target.value = "";
    }
    return (_jsxs("div", { className: styles.root, children: [_jsxs("div", { className: styles.tabs, children: [_jsx("button", { className: filter === "all" ? styles.tabActive : styles.tab, onClick: () => setFilter("all"), children: "Todos" }), CATEGORIES.map((c) => (_jsx("button", { className: filter === c.key ? styles.tabActive : styles.tab, onClick: () => setFilter(c.key), children: c.label }, c.key)))] }), _jsxs("div", { className: styles.grid, children: [filtered.map((avatar) => (_jsx("button", { className: value === avatar.id ? styles.cellActive : styles.cell, title: avatar.label, onClick: () => { setPreview(null); onChange(avatar.id); }, children: _jsx("img", { src: avatar.file, alt: avatar.label, width: 48, height: 48, draggable: false }) }, avatar.id))), _jsxs("button", { className: styles.uploadCell, title: "Subir mi imagen", onClick: () => fileRef.current?.click(), disabled: uploading, children: [preview ? (_jsx("img", { src: preview, alt: "Custom", width: 48, height: 48, draggable: false })) : (_jsx("span", { className: styles.uploadIcon, children: uploading ? "…" : "+" })), _jsx("span", { className: styles.uploadLabel, children: "Custom" })] })] }), _jsx("input", { ref: fileRef, type: "file", accept: "image/*", style: { display: "none" }, onChange: handleFileUpload }), value && (_jsx("p", { className: styles.hint, children: value.startsWith("data:") ? "Avatar personalizado activo" : `Seleccionado: ${GALLERY_AVATARS.find((a) => a.id === value)?.label ?? value}` }))] }));
}
