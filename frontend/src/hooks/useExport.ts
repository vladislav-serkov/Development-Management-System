import { useMutation } from "@tanstack/react-query"
import { exportProjectZip } from "@/api/documents"
import { isDesktop } from "@/lib/platform"

async function saveBlobDesktop(blob: Blob, defaultName: string): Promise<void> {
  const { save } = await import("@tauri-apps/plugin-dialog")
  const { writeFile } = await import("@tauri-apps/plugin-fs")

  const path = await save({
    defaultPath: defaultName,
    filters: [{ name: "Zip archive", extensions: ["zip"] }],
  })
  if (!path) return

  const bytes = new Uint8Array(await blob.arrayBuffer())
  await writeFile(path, bytes)
}

function saveBlobWeb(blob: Blob, defaultName: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = defaultName
  a.click()
  URL.revokeObjectURL(url)
}

export function useExportProjectZip(projectSlug: string) {
  return useMutation({
    mutationFn: () => exportProjectZip(projectSlug),
    onSuccess: async (blob) => {
      const defaultName = `${projectSlug}.zip`
      if (isDesktop()) {
        await saveBlobDesktop(blob, defaultName)
      } else {
        saveBlobWeb(blob, defaultName)
      }
    },
  })
}
