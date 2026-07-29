import { notFound } from 'next/navigation';
import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';
import { MDXRemote } from 'next-mdx-remote/rsc';

export default async function Page(props: {
  params: Promise<{ slug?: string[] }>;
}) {
  const params = await props.params;
  const slugArray = params.slug || ['index'];
  const slugPath = slugArray.join('/');

  const docsDirectory = path.join(process.cwd(), 'content/docs');
  const fullPath = path.join(docsDirectory, `${slugPath}.mdx`);

  if (!fs.existsSync(fullPath)) {
    notFound();
  }

  const fileContents = fs.readFileSync(fullPath, 'utf8');
  const { content, data } = matter(fileContents);

  return (
    <>
      <h1 className="text-4xl font-display font-bold mb-4">{data.title}</h1>
      {data.description && <p className="text-xl text-text-secondary mb-8">{data.description}</p>}
      <MDXRemote source={content} />
    </>
  );
}

export async function generateMetadata(props: {
  params: Promise<{ slug?: string[] }>;
}) {
  const params = await props.params;
  const slugArray = params.slug || ['index'];
  const slugPath = slugArray.join('/');

  const docsDirectory = path.join(process.cwd(), 'content/docs');
  const fullPath = path.join(docsDirectory, `${slugPath}.mdx`);

  if (!fs.existsSync(fullPath)) {
    return { title: 'Not Found' };
  }

  const fileContents = fs.readFileSync(fullPath, 'utf8');
  const { data } = matter(fileContents);

  return {
    title: data.title ? `${data.title} | Synap Docs` : 'Synap Docs',
    description: data.description || 'Synap Documentation',
  };
}
