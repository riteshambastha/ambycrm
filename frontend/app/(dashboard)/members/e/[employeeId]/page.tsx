import { ProfilePageContent } from "@/components/members/ProfilePageContent";

interface Props {
  params: Promise<{ employeeId: string }>;
}

export default async function EmployeeProfilePage({ params }: Props) {
  const { employeeId } = await params;
  return <ProfilePageContent personId={employeeId} personType="employee" />;
}
