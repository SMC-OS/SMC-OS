export default function Home() {
  return (
    <main className="min-h-screen bg-black text-white flex items-center justify-center">
      <div className="text-center px-6">
        <h1 className="text-6xl font-bold tracking-tight">
          SMC <span className="text-yellow-500">OS</span>
        </h1>

        <p className="mt-6 max-w-2xl text-lg text-gray-400">
          More than an app.
          <br />
          A better way to build.
        </p>

        <div className="mt-10">
          <button className="rounded-xl bg-yellow-500 px-6 py-3 font-semibold text-black hover:bg-yellow-400 transition">
            Coming Soon
          </button>
        </div>
      </div>
    </main>
  );
}