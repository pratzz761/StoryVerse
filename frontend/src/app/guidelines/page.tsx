import Link from "next/link";
export default function Guidelines() {
  return <article className="writing-page form-stack"><h1>Community guidelines</h1>
    <p>Share original fiction and media you have permission to publish. Collaborate respectfully and review AI output before approving it.</p>
    <p>Do not post harassment, hate, threats, sexual exploitation, sexual content involving minors, graphic abuse, private personal information, scams or spam. Do not impersonate another person or publish material that infringes their rights.</p>
    <p>Use Report story in a story room to contact the moderation team. Reports are private, and duplicate reports do not increase their priority. Moderators may hide a story and its public media while keeping its history. This hackathon uses human moderation; review is not instantaneous.</p>
    <p>Keep sensitive personal information out of AI prompts. The configured text provider (AMD Token Factory or Gemini) receives fictional text/context after your consent. Review its API terms; Google's unpaid service may use text to improve its products. Local artwork also needs your review for errors and character consistency.</p>
    <Link href="/" className="text-button">Back to Explore</Link></article>;
}
