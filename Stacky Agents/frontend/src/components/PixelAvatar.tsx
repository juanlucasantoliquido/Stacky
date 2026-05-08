import React from "react";
import { resolveAvatarSrc } from "../services/avatarGallery";
import styles from "./PixelAvatar.module.css";

type AvatarSize = "sm" | "md" | "lg";

interface PixelAvatarProps {
  /** Gallery ID (e.g. "dev-1") or base64 data-URI, or null for placeholder */
  value: string | null;
  size?: AvatarSize;
  /** Display name for alt text */
  name?: string;
  className?: string;
}

const SIZE_PX: Record<AvatarSize, number> = { sm: 32, md: 64, lg: 96 };

export default function PixelAvatar({ value, size = "md", name, className }: PixelAvatarProps) {
  const px = SIZE_PX[size];
  const src = resolveAvatarSrc(value);

  if (!src) {
    return (
      <div
        className={`${styles.placeholder} ${styles[size]} ${className ?? ""}`}
        style={{ width: px, height: px }}
        title={name ?? "Avatar"}
      >
        <span className={styles.initials}>
          {name ? name.slice(0, 2).toUpperCase() : "??"}
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={name ? `Avatar de ${name}` : "Avatar"}
      width={px}
      height={px}
      className={`${styles.img} ${styles[size]} ${className ?? ""}`}
      draggable={false}
    />
  );
}
