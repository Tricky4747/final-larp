import "./globals.css";
export const metadata = { title: "Business Agent Platform", description: "Drop an idea. Agents validate, build, and test it." };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en"><body>{children}</body></html>);
}
