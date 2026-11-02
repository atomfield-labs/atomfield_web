// The words on the About us page, kept apart from its layout. Each is
// something the product really does.
export const ABOUT = {
  headline: 'Scientific pipelines on the computers you already use',
  intro:
    'AtomField turns calculation scripts into pipelines that anyone in a ' +
    'lab can build, run and repeat from a browser, while the jobs run on ' +
    "the lab's own cluster.",
  audience:
    'It is for research groups who run the same kinds of calculations ' +
    'again and again, and want them written down once and run the same ' +
    'way every time.',
  promises: [
    {
      title: 'Your compute',
      text:
        'Jobs run on your own cluster or computer, through a small program ' +
        'that only makes outgoing connections. AtomField never sees your ' +
        'cluster password.',
    },
    {
      title: 'Your results',
      text:
        'Results stay where the job ran. AtomField shows the plots and ' +
        'files each step writes, and gives you the command to copy the rest.',
    },
    {
      title: 'Repeatable runs',
      text:
        'Every run is pinned to the exact version of the scripts that made ' +
        'it, and each job folder records it.',
    },
  ],
  builtBy: {
    name: 'Ujjawal Modanwal',
    role: 'Sole developer, and the idea behind the product.',
    email: 'ujjawal.m.wal@gmail.com',
    // A paragraph under the name, shown once this is filled in.
    bio: '',
  },
};
