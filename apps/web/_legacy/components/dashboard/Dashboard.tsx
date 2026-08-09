import Topbar from "../layout/Topbar";
import Card from "../ui/Card";
export default function Dashboard() {
  return (
    <section className="flex-1 bg-zinc-950">
     <Topbar />

<div className="p-10">
    <h2 className="text-4xl font-bold">
      Welcome back, Simo 👋
    </h2>

    <p className="mt-3 text-zinc-400">
      Let&#39;s build something amazing today.
    </p>

            <div className="grid grid-cols-4 gap-6 mt-10">
        <Card title="Revenue" value="£124,580" trend="+12.4%" />
<Card title="Projects" value="18" trend="+3 this week" />
<Card title="Quotes" value="42" trend="+8 pending" />
<Card title="Customers" value="136" trend="+15 this month" />
      </div>
    </div>
</section>
  );
}
