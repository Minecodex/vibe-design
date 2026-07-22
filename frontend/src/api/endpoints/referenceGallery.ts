import { apiClient } from '../client'

export type ReferenceTaxonomyKind = 'category' | 'style' | 'classification'

export interface ReferenceTaxonomyRead {
  id: number
  kind: ReferenceTaxonomyKind
  name: string
  prompt?: string | null
  image_count: number
  created_at: string
  updated_at: string
}

export interface ReferenceImageRead {
  id: number
  url: string
  name: string
  category_id: number
  category_name: string
  style_id?: number | null
  style_name?: string | null
  style_prompt?: string | null
  classification_id?: number | null
  classification_name?: string | null
  classification_prompt?: string | null
  list_preview_url?: string | null
  list_preview_status?: 'ready' | 'pending' | 'missing' | null
  created_at: string
  updated_at: string
}

export interface ImageSearchParams {
  category_id?: number
  style_id?: number
  classification_id?: number
  skip?: number
  limit?: number
}

export interface ReferenceImageUpdatePayload {
  name?: string | null
  category_id?: number | null
  style_id?: number | null
  classification_id?: number | null
}

export const referenceGalleryApi = {
  listTaxonomies: (kind: ReferenceTaxonomyKind) =>
    apiClient.get<ReferenceTaxonomyRead[]>('/reference-gallery/taxonomies', { params: { kind } }),
  createTaxonomy: (kind: ReferenceTaxonomyKind, name: string, prompt?: string | null) =>
    apiClient.post<ReferenceTaxonomyRead>('/reference-gallery/taxonomies', { kind, name, prompt }),
  updateTaxonomy: (taxonomyId: number, data: { name?: string | null; prompt?: string | null }) =>
    apiClient.patch<ReferenceTaxonomyRead>(`/reference-gallery/taxonomies/${taxonomyId}`, data),
  deleteTaxonomy: (taxonomyId: number) =>
    apiClient.delete(`/reference-gallery/taxonomies/${taxonomyId}`),

  listCategories: () => referenceGalleryApi.listTaxonomies('category'),
  listStyles: () => referenceGalleryApi.listTaxonomies('style'),
  listClassifications: () => referenceGalleryApi.listTaxonomies('classification'),
  createCategory: (name: string) => referenceGalleryApi.createTaxonomy('category', name, null),
  updateCategory: (categoryId: number, name: string) => referenceGalleryApi.updateTaxonomy(categoryId, { name }),
  deleteCategory: (categoryId: number) => referenceGalleryApi.deleteTaxonomy(categoryId),

  listImages: (params?: ImageSearchParams) =>
    apiClient.get<ReferenceImageRead[]>('/reference-gallery/images', { params }),
  updateImage: (imageId: number, data: ReferenceImageUpdatePayload) =>
    apiClient.patch<ReferenceImageRead>(`/reference-gallery/images/${imageId}`, data),
  deleteImage: (imageId: number) =>
    apiClient.delete(`/reference-gallery/images/${imageId}`),
  uploadImages: (
    files: File[],
    categoryId: number,
    styleId?: number | null,
    classificationId?: number | null,
  ) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    return apiClient.post<ReferenceImageRead[]>('/reference-gallery/uploads', form, {
      params: {
        category_id: categoryId,
        style_id: styleId || undefined,
        classification_id: classificationId || undefined,
      },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
