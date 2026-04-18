import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { CreateDependencyRequest, DependencyType } from "@/types/api"

interface CreateDependencyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  depType: DependencyType
  onSubmit: (req: CreateDependencyRequest) => void
  isPending?: boolean
}

const depTypeLabels: Record<DependencyType, string> = {
  db_table: "таблицу",
  external_api: "API",
  cache: "кэш",
  kafka_topic: "топик",
}

export function CreateDependencyDialog({ open, onOpenChange, depType, onSubmit, isPending }: CreateDependencyDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [method, setMethod] = useState("GET")
  const [serviceName, setServiceName] = useState("")

  const reset = () => {
    setName("")
    setDescription("")
    setMethod("GET")
    setServiceName("")
  }

  const handleSubmit = () => {
    if (!name.trim()) return

    const req: CreateDependencyRequest = {
      dep_type: depType,
      name: name.trim(),
      description: description.trim(),
      ...(depType === "external_api" && { method, service_name: serviceName.trim() }),
    }

    onSubmit(req)
    reset()
  }

  const handleOpenChange = (value: boolean) => {
    if (!value) reset()
    onOpenChange(value)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Добавить {depTypeLabels[depType]}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Название *</label>
            <Input
              placeholder="Название"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit() }}
              autoFocus
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Описание</label>
            <Input
              placeholder="Описание"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {depType === "external_api" && (
            <>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Метод</label>
                <select
                  className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none"
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                >
                  {["GET", "POST", "PUT", "DELETE", "PATCH"].map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Имя сервиса</label>
                <Input
                  placeholder="Имя сервиса"
                  value={serviceName}
                  onChange={(e) => setServiceName(e.target.value)}
                />
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isPending}>
            Отмена
          </Button>
          <Button onClick={handleSubmit} disabled={isPending || !name.trim()}>
            {isPending ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
