export const ssr = false

export async function load({ params }) {
    return {
        nodeId: params.nodeId,
        slug: params.slug,
        groupId: Number(params.id),
    }
}
