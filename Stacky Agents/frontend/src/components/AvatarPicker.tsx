import React, { useRef, useState } from "react";
import { GALLERY_AVATARS } from "../services/avatarGallery";
import styles from "./AvatarPicker.module.css";

interface AvatarPickerProps {
  value: string | null;
  onChange: (avatarIdOrBase64: string) => void;
}

const CATEGORIES = [
  { key: "dev",     label: "Dev" },
  { key: "analyst", label: "Analista" },
  { key: "qa",      label: "QA" },
  { key: "pm",      label: "PM/TL" },
  { key: "ops",     label: "Ops/BD" },
  { key: "design",  label: "Diseño" },
  { key: "special", label: "Especial" },
] as const;

export default function AvatarPicker({ value, onChange }: AvatarPickerProps) {
  const [filter, setFilter] = useState<string>("all");
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered =
    filter === "all" ? GALLERY_AVATARS : GALLERY_AVATARS.filter((a) => a.category === filter);

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);

    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = 64;
        canvas.height = 64;
        const ctx = canvas.getContext("2d")!;
        // nearest-neighbor pixelated scaling
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(img, 0, 0, 64, 64);
        const base64 = canvas.toDataURL("image/png");
        setPreview(base64);
        onChange(base64);
        setUploading(false);
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
    // reset so same file can be re-selected
    e.target.value = "";
  }

  return (
    <div className={styles.root}>
      {/* Filter tabs */}
      <div className={styles.tabs}>
        <button
          className={filter === "all" ? styles.tabActive : styles.tab}
          onClick={() => setFilter("all")}
        >
          Todos
        </button>
        {CATEGORIES.map((c) => (
          <button
            key={c.key}
            className={filter === c.key ? styles.tabActive : styles.tab}
            onClick={() => setFilter(c.key)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Gallery grid */}
      <div className={styles.grid}>
        {filtered.map((avatar) => (
          <button
            key={avatar.id}
            className={value === avatar.id ? styles.cellActive : styles.cell}
            title={avatar.label}
            onClick={() => { setPreview(null); onChange(avatar.id); }}
          >
            <img
              src={avatar.file}
              alt={avatar.label}
              width={48}
              height={48}
              draggable={false}
            />
          </button>
        ))}

        {/* Custom upload slot */}
        <button
          className={styles.uploadCell}
          title="Subir mi imagen"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          {preview ? (
            <img src={preview} alt="Custom" width={48} height={48} draggable={false} />
          ) : (
            <span className={styles.uploadIcon}>{uploading ? "…" : "+"}</span>
          )}
          <span className={styles.uploadLabel}>Custom</span>
        </button>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={handleFileUpload}
      />

      {value && (
        <p className={styles.hint}>
          {value.startsWith("data:") ? "Avatar personalizado activo" : `Seleccionado: ${GALLERY_AVATARS.find((a) => a.id === value)?.label ?? value}`}
        </p>
      )}
    </div>
  );
}
