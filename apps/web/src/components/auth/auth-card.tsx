/**
 * The frame shared by sign-in and account setup.
 *
 * One narrow column, the mark at the top, nothing else. Both screens are
 * reached by people who are not yet signed in and have one thing to do, so
 * there is nothing on them that is not part of doing it.
 */
export function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <main className="grid min-h-screen place-items-center bg-background px-6 py-10">
      <div className="w-full max-w-[300px]">
        <div className="mb-10 flex items-center justify-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-primary">
            <span className="block size-3 rotate-45 rounded-[2px] border-2 border-primary-foreground" />
          </span>
          <span className="text-lg font-semibold tracking-tight">Approach</span>
        </div>
        {children}
      </div>
    </main>
  );
}
