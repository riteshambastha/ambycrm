import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted">
      <div className="w-full max-w-md space-y-6 p-4">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">AmbyChat</h1>
          <p className="text-muted-foreground text-sm">
            AI-powered hub for your enterprise tools
          </p>
        </div>
        <SignIn />
      </div>
    </div>
  );
}
