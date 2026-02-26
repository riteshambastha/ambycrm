import { ProfilePageContent } from "@/components/members/ProfilePageContent";

interface Props {
  params: Promise<{ memberId: string }>;
}

export default async function MemberProfilePage({ params }: Props) {
  const { memberId } = await params;
  return <ProfilePageContent personId={memberId} personType="member" />;
}
