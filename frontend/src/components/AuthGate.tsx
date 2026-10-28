import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { UNAUTHORIZED_EVENT } from "@/api/client"
import { ME_KEY, useLogin, useMe } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

export function AuthGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const { data: me, isLoading, error } = useMe()

  useEffect(() => {
    // Session expired or revoked mid-use → back to the login screen
    const onUnauthorized = () => qc.setQueryData(ME_KEY, null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [qc])

  if (isLoading) return <div className="p-8 text-sm text-muted-foreground">Загрузка...</div>
  if (error) return <div className="p-8 text-sm text-destructive">Сервер недоступен: {error.message}</div>
  if (me === null) return <LoginScreen />
  return <>{children}</>
}

function LoginScreen() {
  const loginMutation = useLogin()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    loginMutation.mutate({ username: username.trim(), password })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Development Management System</CardTitle>
          <p className="text-sm text-muted-foreground">Войдите, чтобы продолжить</p>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
            <Input
              autoFocus
              autoComplete="username"
              placeholder="Логин"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <Input
              type="password"
              autoComplete="current-password"
              placeholder="Пароль"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {loginMutation.error && <p className="text-sm text-destructive">{loginMutation.error.message}</p>}
            <Button type="submit" disabled={loginMutation.isPending}>
              {loginMutation.isPending ? "Вход..." : "Войти"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
