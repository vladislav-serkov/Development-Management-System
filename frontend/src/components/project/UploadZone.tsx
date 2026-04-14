import { useDropzone } from "react-dropzone"
import { cn } from "@/lib/utils"

interface UploadZoneProps {
  onUpload: (file: File) => void
  isUploading: boolean
}

export function UploadZone({ onUpload, isUploading }: UploadZoneProps) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
    disabled: isUploading,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        onUpload(acceptedFiles[0])
      }
    },
  })

  return (
    <div
      {...getRootProps()}
      className={cn(
        "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
        isDragActive
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-muted-foreground/50",
        isUploading && "opacity-50 cursor-not-allowed"
      )}
    >
      <input {...getInputProps({ className: "hidden" })} />
      {isUploading ? (
        <p className="text-sm text-muted-foreground">Загрузка PDF...</p>
      ) : isDragActive ? (
        <p className="text-sm text-primary">Отпустите PDF, чтобы загрузить</p>
      ) : (
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">
            Перетащите PDF сюда или нажмите для загрузки
          </p>
          <p className="text-xs text-muted-foreground/60">Поддерживаются только PDF</p>
        </div>
      )}
    </div>
  )
}
