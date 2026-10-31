import apiClient from '../client';
import type { LabDetail, LabSummary, Role } from '../../types/api';

// What changes about someone in a lab; what is left out stays.
export interface PersonChange {
  workflows?: string[];
  role?: Exclude<Role, 'owner'>;
}

// Labs: the owner makes them and gives them workflows; a lab's admin
// adds its people and ticks workflows for each. Every change answers
// with the lab as it now stands.
export const labsService = {
  async list(): Promise<LabSummary[]> {
    const response = await apiClient.get<LabSummary[]>('/api/labs');
    return response.data;
  },

  async create(name: string, adminEmail: string): Promise<LabDetail> {
    const response = await apiClient.post<LabDetail>('/api/labs', {
      name,
      admin_email: adminEmail,
    });
    return response.data;
  },

  async get(labId: string): Promise<LabDetail> {
    const response = await apiClient.get<LabDetail>(`/api/labs/${labId}`);
    return response.data;
  },

  async change(
    labId: string,
    change: { name?: string; workflows?: string[] }
  ): Promise<LabDetail> {
    const response = await apiClient.patch<LabDetail>(
      `/api/labs/${labId}`,
      change
    );
    return response.data;
  },

  async addPeople(labId: string, emails: string[]): Promise<LabDetail> {
    const response = await apiClient.post<LabDetail>(
      `/api/labs/${labId}/people`,
      { emails }
    );
    return response.data;
  },

  async changePerson(
    labId: string,
    personId: string,
    change: PersonChange
  ): Promise<LabDetail> {
    const response = await apiClient.patch<LabDetail>(
      `/api/labs/${labId}/people/${personId}`,
      change
    );
    return response.data;
  },

  async removePerson(labId: string, personId: string): Promise<LabDetail> {
    const response = await apiClient.delete<LabDetail>(
      `/api/labs/${labId}/people/${personId}`
    );
    return response.data;
  },
};
