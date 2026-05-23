import { jsx as _jsx } from "react/jsx-runtime";
import { resolveAvatarSrc } from "../services/avatarGallery";
import styles from "./PixelAvatar.module.css";
const SIZE_PX = { sm: 32, md: 64, lg: 96 };
export default function PixelAvatar({ value, size = "md", name, className }) {
    const px = SIZE_PX[size];
    const src = resolveAvatarSrc(value);
    if (!src) {
        return (_jsx("div", { className: `${styles.placeholder} ${styles[size]} ${className ?? ""}`, style: { width: px, height: px }, title: name ?? "Avatar", children: _jsx("span", { className: styles.initials, children: name ? name.slice(0, 2).toUpperCase() : "??" }) }));
    }
    return (_jsx("img", { src: src, alt: name ? `Avatar de ${name}` : "Avatar", width: px, height: px, className: `${styles.img} ${styles[size]} ${className ?? ""}`, draggable: false }));
}
